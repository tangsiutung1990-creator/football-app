from flask import Flask, jsonify
from flask_cors import CORS
from football import get_todays_matches

app = Flask(__name__)
# Enable CORS so the React frontend (port 3000/5173) can talk to this backend (port 5000)
CORS(app)

@app.route('/api/matches', methods=['GET'])
def matches():
    try:
        data = get_todays_matches()
        return jsonify(data)
    except Exception as e:
        print(f"Error fetching matches: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/')
def home():
    return "AI Football Predictor API is running!"

if __name__ == '__main__':
    # Run the server on port 5000
    app.run(debug=True, port=5000)
