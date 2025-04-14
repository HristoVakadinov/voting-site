from datetime import datetime
import os
from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from bson import json_util
from flask_httpauth import HTTPBasicAuth


app = Flask(__name__)
CORS(app)  

client = MongoClient(os.environ.get('MONGO_URI'))
db = client.voting_db  

auth = HTTPBasicAuth()
ADMIN_SECRET = os.environ.get('ADMIN_SECRET_KEY')

@auth.verify_password
def verify_password(username, password):
    return username == os.environ.get('ADMIN_PASSWORD') and password == os.environ.get('ADMIN_PASS')

@app.route('/admin/<secret>')
@auth.login_required
def admin_page(secret):
    if secret != ADMIN_SECRET:
        return "Невалиден административен ключ", 403
    
    voters = list(db.votes.find({}, {"_id": 0, "username": 1, "language": 1, "timestamp": 1}))
    
    
    html_template = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Административен панел</title>
        <style>
            body { font-family: Arial; padding: 20px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
        </style>
    </head>
    <body>
        <h1>Списък с гласували (общо: {{ count }})</h1>
        <table>
            <tr>
                <th>Потребител</th>
                <th>Език</th>
                <th>Дата/час</th>
            </tr>
            {% for voter in voters %}
            <tr>
                <td>{{ voter.username }}</td>
                <td>{{ voter.language }}</td>
                <td>{{ voter.timestamp.strftime('%Y-%m-%d %H:%M') }}</td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """
    
    return render_template_string(html_template, voters=voters, count=len(voters))

LANGUAGES = ["Python", "C", "C++", "C#", "Java"]

if 'votes' not in db.list_collection_names():
    db.create_collection('votes')
    db.votes.create_index([("location", "2dsphere")])  
    print("Колекцията 'votes' беше създадена!")

@app.route('/vote', methods=['POST'])
def add_vote():
    try:
        data = request.json
        
        # Валидация
        if not data.get("username"):
            return jsonify({"error": "Моля, въведете име"}), 400
            
        if data.get("language") not in LANGUAGES:
            return jsonify({"error": "Невалиден език за програмиране"}), 400

        # Запис на гласа
        vote_data = {
            "username": data["username"],
            "language": data["language"],
            "timestamp": datetime.utcnow()
        }
        
        db.votes.insert_one(vote_data)
        return jsonify({"status": "success"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/results', methods=['GET'])
def get_results():
    pipeline = [
        {"$group": {"_id": "$language", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    results = list(db.votes.aggregate(pipeline))
    return jsonify({"languages": LANGUAGES, "results": results})

@app.route('/timeline', methods=['GET'])
def get_timeline():
    pipeline = [
        {"$project": {
            "hour": {"$hour": "$timestamp"},
            "language": 1
        }},
        {"$group": {
            "_id": {"hour": "$hour", "language": "$language"},
            "count": {"$sum": 1}
        }},
        {"$sort": {"_id.hour": 1}}
    ]
    timeline = list(db.votes.aggregate(pipeline))
    return jsonify(timeline)

@app.route('/voters', methods=['GET'])
def get_voters():
    pipeline = [
        {"$group": {
            "_id": "$language",
            "voters": {"$push": "$username"},
            "count": {"$sum": 1}
        }}
    ]
    voters = list(db.votes.aggregate(pipeline))
    return jsonify(voters)

@app.route('/api/votes/locations')
def get_locations():
    pipeline = [
        {"$match": {"location": {"$exists": True}}},
        {"$group": {
            "_id": {"language": "$language", "loc": "$location"},
            "count": {"$sum": 1}
        }},
        {"$project": {
            "language": "$_id.language",
            "lat": {"$arrayElemAt": ["$_id.loc.coordinates", 1]},
            "lng": {"$arrayElemAt": ["$_id.loc.coordinates", 0]},
            "count": 1,
            "_id": 0
        }}
    ]
    return jsonify(list(db.votes.aggregate(pipeline)))

@app.route('/map-data')
def get_map_data():
    pipeline = [
        {
            "$match": {
                "location": {"$exists": True}
            }
        },
        {
            "$group": {
                "_id": {
                    "language": "$language",
                    "coordinates": "$location.coordinates"
                },
                "count": {"$sum": 1}
            }
        },
        {
            "$project": {
                "language": "$_id.language",
                "lng": {"$arrayElemAt": ["$_id.coordinates", 0]},
                "lat": {"$arrayElemAt": ["$_id.coordinates", 1]},
                "count": 1,
                "_id": 0
            }
        }
    ]
    return jsonify(list(db.votes.aggregate(pipeline)))
    

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
