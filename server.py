from flask import Flask, jsonify, send_from_directory, request, session
from werkzeug.security import generate_password_hash, check_password_hash
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
import requests

# ---------------- App setup ----------------
app = Flask(__name__, static_folder='frontend')
app.secret_key = "super-secret-key"  # needed for login sessions
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///watchlist.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

CORS(app, resources={r"/*": {"origins": "*"}})

# ---------------- Models ----------------
class Watchlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(db.Integer, unique=True, nullable=False)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

# ---------------- TMDB Setup ----------------
TMDB_API_KEY = "b01539baa65799c628aa11db1b63b1ad"
TMDB_BASE_URL = "https://api.themoviedb.org/3"

GENRE_ID_MAP = {
    "action": 28, "adventure": 12, "comedy": 35, "drama": 18,
    "fantasy": 14, "horror": 27, "mystery": 9648, "romance": 10749,
    "sci-fi": 878, "thriller": 53, "animation": 16, "documentary": 99,
}

# ---------------- Requests Session ----------------
http_session = requests.Session()  # renamed to avoid conflict with Flask session
http_session.keep_alive = False

# ---------------- Helpers ----------------
def format_movies(movies):
    return [
        {
            "id": m.get("id"),
            "title": m.get("title"),
            "poster_path": m.get("poster_path"),
            "vote_average": m.get("vote_average", 0),
            "genre_ids": m.get("genre_ids", [])
        }
        for m in movies
    ]

# ---------------- Movie Routes ----------------
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/recommendations/<genre>', methods=['GET'])
def get_recommendations_by_genre(genre):
    page = request.args.get("page", 1)
    genre_id = GENRE_ID_MAP.get(genre.lower())
    if not genre_id:
        return jsonify({"error": f"Genre '{genre}' not found"}), 404

    url = f"{TMDB_BASE_URL}/discover/movie?api_key={TMDB_API_KEY}&with_genres={genre_id}&sort_by=popularity.desc&page={page}"
    print(f"[DEBUG] Fetching {genre} (ID {genre_id}) -> {url}")

    try:
        response = http_session.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        return jsonify(format_movies(data.get("results", [])))
    except requests.exceptions.Timeout:
        return jsonify({"error": f"TMDB request for genre '{genre}' timed out"}), 504
    except Exception as e:
        print(f"[ERROR] Failed to fetch {genre}: {e}")
        return jsonify({"error": f"Failed to fetch movies for genre '{genre}'"}), 500

@app.route('/trending', methods=['GET'])
def get_trending():
    page = request.args.get("page", 1)
    url = f"{TMDB_BASE_URL}/trending/movie/week?api_key={TMDB_API_KEY}&page={page}"
    print(f"[DEBUG] Trending -> {url}")
    try:
        response = http_session.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        return jsonify(format_movies(data.get("results", [])))
    except Exception as e:
        print(f"[ERROR] Trending failed: {e}")
        return jsonify({"error": "Failed to fetch trending movies"}), 500

@app.route('/new-releases', methods=['GET'])
def get_new_releases():
    page = request.args.get("page", 1)
    url = f"{TMDB_BASE_URL}/discover/movie?api_key={TMDB_API_KEY}&sort_by=release_date.desc&page={page}"
    print(f"[DEBUG] New Releases -> {url}")
    try:
        response = http_session.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        return jsonify(format_movies(data.get("results", [])))
    except Exception as e:
        print(f"[ERROR] New releases failed: {e}")
        return jsonify({"error": "Failed to fetch new releases"}), 500

@app.route('/top-rated', methods=['GET'])
def get_top_rated():
    page = request.args.get("page", 1)
    url = f"{TMDB_BASE_URL}/movie/top_rated?api_key={TMDB_API_KEY}&page={page}"
    print(f"[DEBUG] Top Rated -> {url}")
    try:
        response = http_session.get(url, timeout=15)
        response.raise_for_status()
        data = response.json()
        return jsonify(format_movies(data.get("results", [])))
    except Exception as e:
        print(f"[ERROR] Top rated failed: {e}")
        return jsonify({"error": "Failed to fetch top rated movies"}), 500

@app.route('/movie/<int:movie_id>', methods=['GET'])
def get_movie_details(movie_id):
    try:
        details_url = f"{TMDB_BASE_URL}/movie/{movie_id}?api_key={TMDB_API_KEY}"
        credits_url = f"{TMDB_BASE_URL}/movie/{movie_id}/credits?api_key={TMDB_API_KEY}"
        print(f"[DEBUG] Fetching details for movie {movie_id}")

        details_res = http_session.get(details_url, timeout=15)
        details_res.raise_for_status()
        movie_details = details_res.json()

        credits_res = http_session.get(credits_url, timeout=15)
        credits_res.raise_for_status()
        credits_data = credits_res.json()
        cast = credits_data.get("cast", [])

        top_cast = [
            {"name": c.get("name"), "character": c.get("character"), "profile_path": c.get("profile_path")}
            for c in cast[:5]
        ]
        movie_details["cast"] = top_cast

        return jsonify(movie_details)
    except Exception as e:
        print(f"[ERROR] Failed to fetch movie {movie_id}: {e}")
        return jsonify({"error": "Failed to fetch movie details"}), 500

@app.route('/movie/<int:movie_id>/trailer', methods=['GET'])
def get_movie_trailer(movie_id):
    try:
        url = f"{TMDB_BASE_URL}/movie/{movie_id}/videos?api_key={TMDB_API_KEY}&language=en-US"
        print(f"[DEBUG] Fetching trailer for movie {movie_id}")

        res = http_session.get(url, timeout=15)
        res.raise_for_status()
        data = res.json()

        trailers = [v for v in data.get("results", []) if v.get("site") == "YouTube" and v.get("type") == "Trailer"]

        if trailers:
            trailer_key = trailers[0]["key"]
            return jsonify({"youtube_url": f"https://www.youtube.com/watch?v={trailer_key}"})
        else:
            return jsonify({"error": "No trailer found"}), 404
    except Exception as e:
        print(f"[ERROR] Trailer fetch failed for movie {movie_id}: {e}")
        return jsonify({"error": "Failed to fetch trailer"}), 500

# ---------------- Watchlist Routes ----------------
@app.route('/watchlist', methods=['GET'])
def get_watchlist():
    movies = Watchlist.query.all()
    return jsonify([m.movie_id for m in movies])

@app.route('/watchlist/<int:movie_id>', methods=['POST'])
def add_to_watchlist(movie_id):
    if Watchlist.query.filter_by(movie_id=movie_id).first():
        return jsonify({"message": "Already in watchlist"}), 200
    new_entry = Watchlist(movie_id=movie_id)
    db.session.add(new_entry)
    db.session.commit()
    return jsonify({"message": "Movie added", "movie_id": movie_id})

@app.route('/watchlist/<int:movie_id>', methods=['DELETE'])
def remove_from_watchlist(movie_id):
    entry = Watchlist.query.filter_by(movie_id=movie_id).first()
    if entry:
        db.session.delete(entry)
        db.session.commit()
        return jsonify({"message": "Movie removed", "movie_id": movie_id})
    return jsonify({"message": "Movie not found"}), 404

# ---------------- Auth Routes ----------------
@app.route('/register', methods=['POST'])
def register():
    username = request.form.get("username")
    password = request.form.get("password")

    if User.query.filter_by(username=username).first():
        return jsonify({"success": False, "message": "Username already exists"})

    hashed = generate_password_hash(password)
    new_user = User(username=username, password_hash=hashed)
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"success": True, "message": "Registration successful!"})

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get("username")
    password = request.form.get("password")

    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password_hash, password):
        session['username'] = username
        return jsonify({"success": True, "message": f"Welcome {username}!"})
    return jsonify({"success": False, "message": "Invalid credentials"})

@app.route('/login-check')
def login_check():
    return jsonify({"logged_in": 'username' in session})

@app.route('/logout')
def logout():
    session.pop('username', None)
    return jsonify({"success": True, "message": "Logged out"})

# ---------------- Run Server ----------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # creates tables if not exists
    print("Starting CineMatch server on http://127.0.0.1:5000/")
    app.run(debug=True)
