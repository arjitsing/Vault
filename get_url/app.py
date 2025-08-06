from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/get_url', methods=['POST'])
def get_url():
    data = request.get_json()
    
    # Basic check
    if not data or 'name' not in data:
        return jsonify({'error': 'Missing "name" in request body'}), 400
    
    name = data['name']
    
    # Mock logic to generate URL
    generated_url = f"https://cdn.example.com/resources/{name}"
    
    return jsonify({"url": generated_url})

if __name__ == '__main__':
    # Run on HTTP (port 8080)
    app.run(host='0.0.0.0', port=8080)
