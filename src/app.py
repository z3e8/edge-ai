from flask import Flask, jsonify
from model import load_model

app = Flask(__name__)

# load model at startup
try:
    load_model()
except Exception as e:
    print(f"error loading model, exiting: {e}")
    exit(1)

@app.route('/')
def hello():
    return jsonify({"message": "hello world"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)

