import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.utils.markdown import hbold
import aiohttp
from aiogram.types import URLInputFile, FSInputFile
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.utils.keyboard import InlineKeyboardBuilder
import yt_dlp
from pymongo import MongoClient


TOKEN = ""

dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Hello, {hbold(message.from_user.full_name)}!")


client = MongoClient("localhost", 27017)
db = client["music"]
queries = db["queries"]
tracks = db["tracks"]


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
}


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
        'text': message.text,
        # Search type
        'type': 'all',
        # Language
        'lang': 'ru',
        # Domain name
        'external-domain': 'music.yandex.ru',
        # Disable overembed
        'overembed': 'false',
    }

    # Check if the query is already in the database
    query_data = queries.find_one({'query': message.text})
    if query_data is not None:
        # If the query is in the database, use the stored data
        data = query_data['data']
    else:
        # If the query is not in the database, fetch the data and store it
        async with aiohttp.ClientSession() as session:
            # Make request to Yandex Music API
            async with session.post('https://music.yandex.ru/handlers/music-search.jsx', params=payload) as resp:
                # Parse response as JSON
                data = await resp.json()

        # Store the query and the data in the 'queries' collection
        queries.insert_one({'query': message.text, 'data': data})

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
    for track in tracks_info:
        tracks.update_one({'id': track['id']}, {'$set': track}, upsert=True)

    caption = "\n".join(
        # Message with tracks list
        f"{i+1}. {', '.join(artists)} - {title}"
        for i, (title, artists) in enumerate(
            (
                (track["title"], track["artists"])
                for track in tracks_info
            )
        )
    )

    album_builder = MediaGroupBuilder(caption=caption)
    buttons_builder = InlineKeyboardBuilder()
    for index, track in enumerate(tracks_info):
        # Get track cover URL
        cover_uri_data = track["cover_uri"][37:-3]
        cover_url = f"https://avatars.yandex.net/get-music-content/{cover_uri_data}/1000x1000"

        album_builder.add(
            # Media type
            type="photo",
            # Media URL
            media=URLInputFile(cover_url),
        )

        buttons_builder.add(types.InlineKeyboardButton(
            # Button text
            text=str(index+1),
            # Callback data
            callback_data=str(track["id"])
        ))

    await message.answer_media_group(
        media=album_builder.build(),
    )

    await message.answer(
        "Выберите трек",
        reply_markup=buttons_builder.as_markup()
    )


@dp.callback_query()
async def send_track(callback: types.CallbackQuery) -> None:
    """Send track to user by its ID"""
    track_id = int(callback.data)
    track = tracks.find_one({'id': track_id})
    if track:
        search_query = f"{track['title']} {', '.join(track['artists'])}"
        ydl_opts.update({'outtmpl': str(track_id)})
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info and download the track
                ydl.extract_info(search_query, download=True)
        except yt_dlp.DownloadError:
            await callback.message.answer("The track could not be downloaded.")
            return

        track_file = FSInputFile(str(track_id) + '.mp3', filename=search_query)
        
        await callback.message.answer_audio(track_file)
    else:
        # If the track is not found, notify the user
        await callback.message.answer("The track data could not be found.")



async def main():
    bot = Bot(TOKEN, parse_mode=ParseMode.HTML)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
