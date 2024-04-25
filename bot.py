import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.utils.markdown import hbold
import aiohttp
from aiogram.types import URLInputFile, FSInputFile
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yt_dlp
from pymongo import MongoClient
from lyrics_sources import azlyrics, genius, google
from config_reader import address, mongodb_server, mongodb_port, token
import asyncio
import os



ydl_opts = {
    "format": "bestaudio/best",
    "postprocessors": [
        {
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }
    ],
    "default_search": "ytsearch",
    "noplaylist": True,
    "quiet": True,
    "match_filter": yt_dlp.utils.match_filter_func("duration < 600"),
}


dp = Dispatcher()

try:
    logging.info("Connecting to MongoDB")
    client = MongoClient(mongodb_server, mongodb_port)
    db = client["music"]
    queries = db["queries"]
    tracks = db["tracks"]
except:
    logging.error("Failed to connect to MongoDB")


try:
    logging.info("Initiating Genius API")
    genius.init_genius_api()
except:
    logging.error("Failed to initialize Genius API")


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(
        f"Привет, {hbold(message.from_user.full_name)}! Этот бот представляет собой музыкальный сервис из комбинации различных площадок. Для поиска треков отправьте мне запрос, который содержит название трека и исполнителя. Выберите трек из списка и нажмите на соответствующую кнопку, чтобы получить его текст и mp3. Затем вы можете выбрать откуда получить текст песни, нажав на кнопки в новом сообщении. Начните с отправки запроса для поиска треков!"
    )


@dp.message()
async def echo_music_handler(message: types.Message) -> None:
    """Get top 5 tracks from Yandex Music API and send them as a message.

    The function fetches the data from Yandex Music API and stores it in the database.
    Then it extracts the necessary data from the response, stores it in the 'tracks'
    collection and sends it to the user as a media group with inline buttons.

    The query is stored in the database to reduce the load on the Yandex Music API.
    """
    payload = {
        # Search query
        "text": message.text,
        # Search type
        "type": "all",
        # Language
        "lang": "ru",
        # Domain name
        "external-domain": "music.yandex.ru",
        # Disable overembed
        "overembed": "false",
    }

    # Check if the query is already in the database
    logging.info(f"Query: {message.text}")
    query_data = queries.find_one({"query": message.text})
    if query_data is not None:
        logging.info("Query found in database")
        # If the query is in the database, use the stored data
        data = query_data["data"]
    else:
        logging.info("Query not found in database")
        # If the query is not in the database, fetch the data and store it
        async with aiohttp.ClientSession() as session:
            logging.info("Making request to Yandex Music API")
            # Make request to Yandex Music API
            async with session.post(
                "https://music.yandex.ru/handlers/music-search.jsx", params=payload
            ) as resp:
                # Parse response as JSON
                data = await resp.json()

        # Store the query and the data in the 'queries' collection
        logging.info("Storing query and data in the database")
        queries.insert_one({"query": message.text, "data": data})

    top_tracks = data["tracks"]["items"][:5]

    tracks_info = [
        {
            # Track id
            "id": track["id"],
            # Track title
            "title": track["title"],
            # Artists names
            "artists": [artist["name"] for artist in track["artists"]],
            # Track cover URL
            "cover_uri": track["coverUri"],
        }
        for track in top_tracks
    ]

    # Store the track data in the 'tracks' collection
    logging.info("Storing track data in the database")
    for track in tracks_info:
        tracks.update_one({"id": track["id"]}, {"$set": track}, upsert=True)

    caption = "\n".join(
        # Message with tracks list
        f"{i + 1}. {', '.join(artists)} - {title}"
        for i, (title, artists) in enumerate(
            ((track["title"], track["artists"]) for track in tracks_info)
        )
    )

    album_builder = MediaGroupBuilder(caption=caption)
    buttons_builder = InlineKeyboardBuilder()

    logging.info("Sending tracks_covers as a media group")
    for index, track in enumerate(tracks_info):
        # Get track cover URL
        cover_uri_data = track["cover_uri"][37:-3]
        cover_url = (
            f"https://avatars.yandex.net/get-music-content/{cover_uri_data}/1000x1000"
        )

        album_builder.add(
            # Media type
            type="photo",
            # Media URL
            media=URLInputFile(cover_url),
        )

        buttons_builder.add(
            types.InlineKeyboardButton(
                # Button text
                text=str(index + 1),
                # Callback data
                callback_data=str(track["id"]),
            )
        )

    await message.answer_media_group(
        media=album_builder.build(),
    )

    await message.answer("Выберите трек", reply_markup=buttons_builder.as_markup())


async def get_lyrics(title: str, artist: str) -> str:
    google_lyrics, azlyrics_lyrics, genius_lyrics = None, None, None
    try:
        google_lyrics = google_lyrics = google.get_lyrics(title=title, artist=artist)
    except:
        logging.error("Google lyrics could not be retrieved")

    try:
        azlyrics_lyrics = azlyrics.get_lyrics(title=title, artist=artist)
    except:
        logging.error("Azlyrics lyrics could not be retrieved")

    try:
        genius.init_genius_api()
        genius_lyrics = genius.get_lyrics(title=title, artist=artist)
    except:
        logging.error("Genius lyrics could not be retrieved")

    return google_lyrics, azlyrics_lyrics, genius_lyrics


@dp.callback_query()
async def send_track(callback: types.CallbackQuery) -> None:
    """Send track to user by its ID"""
    try:
        for provider in ["google", "genius", "azlyrics"]:
            if callback.data.startswith(provider):
                track_id = int(callback.data[len(provider) :])
                lyrics = tracks.find_one({"id": track_id}).get(
                    f"{provider}_lyrics", "No lyrics found"
                )
                await callback.message.edit_text(
                    lyrics + f"\n\n{address}track/{track_id}?provider={provider}",
                    reply_markup=callback.message.reply_markup,
                )
                return
    except Exception as error:
        logging.error("Lyrics could not be retrieved: %s", error)

    try:
        track_id = int(callback.data)
    except ValueError:
        logging.error("Invalid track ID: %s", callback.data)
        return

    track = tracks.find_one({"id": track_id})
    title = track["title"]
    artists = ", ".join(track["artists"])
    audio_file_id = track.get("audio_file_id", None)
    logging.info("Getting lyrics for track %s", track_id)

    try:
        buttons_builder = InlineKeyboardBuilder()
        google_lyrics, azlyrics_lyrics, genius_lyrics = await get_lyrics(
            title=title, artist=artists
        )
        tracks.update_one(
            {"id": track_id},
            {
                "$set": {
                    "google_lyrics": google_lyrics,
                    "azlyrics_lyrics": azlyrics_lyrics,
                    "genius_lyrics": genius_lyrics,
                }
            },
        )

        for provider in [
            ("google", google_lyrics),
            ("azlyrics", azlyrics_lyrics),
            ("genius", genius_lyrics),
        ]:
            if provider[1] is not None:
                buttons_builder.add(
                    types.InlineKeyboardButton(
                        # Button text
                        text=provider[0],
                        # Callback data
                        callback_data=provider[0] + str(track_id),
                    )
                )
        await callback.message.answer(
            "Выберите площадку для текста песни",
            reply_markup=buttons_builder.as_markup(),
        )

    except Exception as error:
        logging.error("Lyrics could not be retrieved: %s", error)
        await callback.message.answer("Текст не найден")

    if audio_file_id is None:
        search_query = f"{track['title']} {', '.join(track['artists'])}"
        ydl_opts.update({"outtmpl": f"/static/{str(track_id)}"})
        logging.info(
            "Downloading track %s with search_query %s", track_id, search_query
        )
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info and download the track
                ydl.extract_info(search_query, download=True)
        except yt_dlp.DownloadError as e:
            logging.error("The track could not be downloaded: %s", e)
            await callback.message.answer("Трек не удалось скачать")
            return

        track_file = FSInputFile(str(track_id) + ".mp3", filename=search_query)

        media = await callback.message.answer_audio(track_file)
        audio_file_id = media.audio.file_id
        tracks.update_one({"id": track_id}, {"$set": {"audio_file_id": audio_file_id}})
        print(media.audio.file_id)
    else:
        # If the track is not found, notify the user
        await callback.message.answer_audio(audio_file_id, artists=artists, title=title)


async def run_bot():
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )
    bot = Bot(token)
    await dp.start_polling(bot)

asyncio.run(run_bot())