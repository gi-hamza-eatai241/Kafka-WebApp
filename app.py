import socket
import threading
import time
import json
import requests
from confluent_kafka import Consumer
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from parameters import CONFLUENT_KAFKA_IP_ADDRESS, \
    CONFLUENT_KAFKA_PORT, \
    CONFLUENT_KAFKA_TOPIC, \
    DISPLAY_LIST_SIZE, \
    NETWORK_FAIL_CHECKS, \
    IMAGE_SERVER_ADDRESS, \
    STATUS_THRESHOLD, \
    DGX_IP_ADDRESS, \
    PROJECT_SERVICES_PORT

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# Kafka configuration
kafka_conf = {
    'bootstrap.servers': f'{CONFLUENT_KAFKA_IP_ADDRESS}:{CONFLUENT_KAFKA_PORT}',
    'group.id': 'face_recognition_feedback_message_consumer_group',
    'auto.offset.reset': 'latest',
    'enable.auto.commit': True,
    'session.timeout.ms': 6000,
    'heartbeat.interval.ms': 2000
}

# Create a queue to store messages from kafka
message_queue = []
message_to_display = []
last_update_time = time.time()


def ping_server(ip: str, port: int):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        sock.connect((ip, port))
        return True
    except socket.error:
        return False


def ping_project_services() -> bool:
    ping_status = []
    for service_port in PROJECT_SERVICES_PORT:
        ping_status.append(ping_server(DGX_IP_ADDRESS, service_port))

    if all(ping_status):
        return True

    return False


def post_message_queue_and_get_images(data):
    global message_to_display
    try:
        response = requests.post(IMAGE_SERVER_ADDRESS, data=data)
        if response.status_code == 200:
            message_to_display = response.json()
        else:
            print(f"Status Code: {response.status_code}, Message: {response.reason}")
    except Exception as e:
        print(f"Exception occurred while posting data: {str(e)}")


def consume_messages():
    global message_queue, last_update_time, message_to_display

    # Create Kafka Consumer
    consumer = Consumer(kafka_conf)
    consumer.subscribe([CONFLUENT_KAFKA_TOPIC])

    ping_fail = 0
    connection_failure_message_sent = False

    while True:
        if ping_project_services():
            ping_fail = 0

            if connection_failure_message_sent:
                connection_failure_message_sent = False
                message_queue = []
                message = "Facial Recognition System is Getting Started. Please Wait for 2 Minutes."
                socketio.emit('new_message', {'message': [{'SUCCESS': message}]})
                # last_update_time = time.time()
                time.sleep(2 * 60)
                message = "Facial Recognition System Started. Please Resume Attendance"
                socketio.emit('new_message', {'message': [{'SUCCESS': message}]})
                time.sleep(10)

            message = consumer.poll(0.1)

            if message is None:
                print(message)

            if message is not None and message.value() is not None:
                print(message.value().decode('utf-8'))
                if message.value().decode('utf-8').startswith("Subscribed topic not available:"):
                    message_queue = []

                    while consumer.poll() is None:
                        continue
                else:
                    decoded_message = message.value().decode('utf-8')
                    if decoded_message.split(": ")[0] == "ERROR":
                        message_queue = []
                        socketio.emit('new_message', {'message': [{'ERROR': decoded_message.split(": ")[1]}]})
                    elif decoded_message.split(": ")[0] == "SUCCESS":
                        message_queue = []
                        socketio.emit('new_message', {'message': [{'SUCCESS': decoded_message.split(": ")[1]}]})
                    else:
                        if decoded_message not in message_queue:
                            if len(message_queue) >= DISPLAY_LIST_SIZE:
                                message_queue.pop()
                            message_queue.insert(0, decoded_message)
                            print(message_queue)
                            data = {"messages": message_queue}
                            data = json.dumps(data)
                            post_message_queue_and_get_images(data)
                            last_update_time = time.time()

        else:
            ping_fail += 1
            time.sleep(1)
            if ping_fail >= NETWORK_FAIL_CHECKS and not connection_failure_message_sent:
                message_queue.clear()
                message = "⚠️ Facial Recognition System Temporarily Down for Maintenance or Due to an Unexpected Issue ⚠️"
                socketio.emit('new_message', {'message': [{'ERROR': message}]})
                connection_failure_message_sent = True
                last_update_time = time.time()

        if time.time() - last_update_time >= STATUS_THRESHOLD:
            message_queue = []
            message_to_display = []
            last_update_time = time.time()
            socketio.emit('new_message', {'message': message_to_display})


kafka_consumer_thread = threading.Thread(target=consume_messages)
kafka_consumer_thread.daemon = True
kafka_consumer_thread.start()


@socketio.on('connect')
def handle_connect():
    global message_to_display
    emit('new_message', {'message': message_to_display})


@socketio.on('check_updates')
def handle_check_updates():
    global message_to_display
    emit('new_message', {'message': message_to_display})


@app.route('/')
def index():
    global message_to_display
    return render_template('index.html', message=message_to_display)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9090)
