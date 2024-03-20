import asyncio
import logging
import sys
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.types import Message
from aiogram.utils.markdown import hbold
import aiohttp
from aiogram.types import URLInputFile
from aiogram.utils.media_group import MediaGroupBuilder
from aiogram.utils.keyboard import InlineKeyboardBuilder
import json
import csv

with open("example.csv", "r", encoding="utf-8", newline='') as csvfile:
    reader = csv.DictReader(csvfile)
    payloads = {row["text"]: row["info"] for row in reader}

    
TOKEN = ""

dp = Dispatcher()

@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Hello, {hbold(message.from_user.full_name)}!")

@dp.message()
async def echo_music_handler(message: types.Message) -> None:
    """Get top 5 tracks from Yandex Music API and send them as a message."""
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
    if message.text not in payloads:
        async with aiohttp.ClientSession() as session:
            # Make request to Yandex Music API
            async with session.post('https://music.yandex.ru/handlers/music-search.jsx', params=payload) as resp:
                # Parse response as JSON
                data = await resp.json()
                payloads[message.text] = data
                csvfile = open("example.csv", "w+", encoding="utf-8",newline='')
                writer = csv.writer(csvfile)
                writer.writerow(["text","info"])
                for text in payloads:
                    writer.writerow([text,payloads[text]])
                csvfile.close()
                csvfile = open("example.csv", "r",encoding="utf-8", newline='')
    else:
        if type(payloads[message.text]) is not dict:
            data = eval(payloads[message.text])
        else:
            data = payloads[message.text]

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

        # Use Genius API to get lyrics
        # song = genius.search_song(title=track["title"], artist=', '.join(track["artists"]))
        # if song is not None:
        #     track.update({"Lyrics": song.lyrics})

        buttons_builder.add(types.InlineKeyboardButton(
            # Button text
            text=str(index+1),
            # Callback data
            callback_data="nothing"
        ))

    await message.answer_media_group(
            media=album_builder.build(),
        )
    await message.answer("Выберите трек", reply_markup=buttons_builder.as_markup())


# @dp.callback_query()
# async def send_random_value(callback: types.CallbackQuery):
#     data = json.loads(callback.data)
#     title = data["title"]
#     artists = data["artists"]
#     await callback.message.answer(f"Вы выбрали песню {', '.join(artists)} от {title}")




async def main() -> None:
    bot = Bot(TOKEN, parse_mode=ParseMode.HTML)
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())