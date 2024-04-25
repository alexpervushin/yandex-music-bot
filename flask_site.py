from flask import Flask, render_template_string, request, url_for
from pymongo import MongoClient
from config_reader import host, port

app = Flask(__name__)

client = MongoClient("localhost", 27017)
db = client["music"]
queries = db["queries"]
tracks = db["tracks"]


@app.route("/track/<id>")
async def track(id):
    track = tracks.find_one({"id": int(id)})
    provider = request.args.get("provider", "google")
    lyrics = track.get(f"{provider}_lyrics", "Текст песни не найден").replace("\n", "<br>")
    audio_file_url = url_for("static", filename=f"{id}.mp3")
    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 100vh;">
        <audio controls>
            <source src="{audio_file_url}" type="audio/mpeg">
            Your browser does not support the audio element.
        </audio>
        <p style="text-align: center; padding: 20px;">{lyrics}</p>
    </body>
    </html>
    """
    return render_template_string(html)


app.run(host=host, port=port)
