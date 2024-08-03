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
    IMAGE_SERVER_ADDRESS, \
    STATUS_THRESHOLD, \
    DGX_IP_ADDRESS, \
    NETWORK_FAIL_CHECK, \
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
# Create a queue for the messages to display
messages_to_display = []
# Keep track of last message update time
last_update_time = time.time()
# Flags to keep track of the ERROR and SUCCESS messages sent
connection_failure_message_sent = False
project_services_down_message_sent = False
successful_reconnection_message_sent = not connection_failure_message_sent
project_restart_message_sent = not project_services_down_message_sent

# initialize a kafka_consumer
kafka_consumer = None


def ping_server(ip: str, port: int):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.2)
        sock.connect((ip, port))
        return True
    except socket.error:
        return False


def ping_project_services() -> bool:
    ping_status = []
    for service_port in PROJECT_SERVICES_PORT:
        ping_status.append(ping_server(DGX_IP_ADDRESS, service_port))

    return all(ping_status)


def post_message_queue_and_get_images(data):
    global messages_to_display
    try:
        response = requests.post(IMAGE_SERVER_ADDRESS, data=data)
        if response.status_code == 200:
            messages_to_display = response.json()
        else:
            print(f"Status Code: {response.status_code}, Message: {response.reason}")
    except Exception as e:
        print(f"Exception occurred while posting data: {str(e)}")


def consume_messages():
    global message_queue, last_update_time, messages_to_display, connection_failure_message_sent, project_services_down_message_sent, successful_reconnection_message_sent, project_restart_message_sent
    global kafka_consumer

    server_ping_fail = 0
    services_ping_fail = 0

    while True:
        is_dgx_reachable = ping_server(DGX_IP_ADDRESS, 22)
        print(f"DGX Reachable: {is_dgx_reachable}")
        are_services_running = ping_project_services()
        print(f"Project Running {are_services_running}")

        if is_dgx_reachable:
            server_ping_fail = 0
            if not successful_reconnection_message_sent:
                message_queue = []
                messages_to_display = []
                message = "🛜 Network Reconnection Successful 🛜"
                socketio.emit('new_message', {'message': [{'SUCCESS': message}]})
                successful_reconnection_message_sent = True
                connection_failure_message_sent = False
                print(f"\n{message}\n")

            if are_services_running:
                services_ping_fail = 0
                if not project_restart_message_sent:
                    message_queue = []
                    messages_to_display = []
                    message = "✅ Facial Recognition Attendance System is Getting Started. Please Wait for 2 Minutes ✅"
                    socketio.emit('new_message', {'message': [{'SUCCESS': message}]})
                    print(f"\n{message}\n")
                    time.sleep(2 * 60)

                    message = "Facial Recognition Attendance System Has Been Started. Please Resume Attendance"
                    socketio.emit('new_message', {'message': [{'SUCCESS': message}]})
                    print(f"\n{message}\n")
                    time.sleep(5)

                    project_restart_message_sent = True
                    project_services_down_message_sent = False

                # Create a Kafka Consumer
                kafka_consumer = Consumer(kafka_conf)
                kafka_consumer.subscribe([CONFLUENT_KAFKA_TOPIC])

                message_from_kafka = kafka_consumer.poll(0.2)

                if message_from_kafka is None:
                    print("No message received.")
                else:
                    # Check if it is not an error message sent by Kafka
                    if message_from_kafka.error():
                        # Clear existing messages
                        message_queue = []
                        # while kafka_consumer.poll() is None:
                        #     continue
                    else:
                        decoded_kafka_message = message_from_kafka.value().decode()
                        # Check if coming message is an ERROR message or SUCCESS message
                        if decoded_kafka_message.split(": ")[0] in ["ERROR", "SUCCESS"]:
                            message_queue = []

                            message_queue.insert(0, decoded_kafka_message)
                            message_data_to_send = {"messages": message_queue}
                            json.dumps(message_data_to_send)
                            post_message_queue_and_get_images(message_data_to_send)
                            message_queue = []
                        else:
                            if len(message_queue) >= DISPLAY_LIST_SIZE:
                                message_queue.pop()
                            message_queue.insert(0, decoded_kafka_message)
                            message_data_to_send = {"messages": message_queue}
                            json.dumps(message_data_to_send)
                            post_message_queue_and_get_images(message_data_to_send)
                            last_update_time = time.time()
            else:
                services_ping_fail += 1

                if services_ping_fail >= 3 and not project_services_down_message_sent:
                    message_queue = []
                    messages_to_display = []
                    message = "⚠️ Facial Recognition System Temporarily Down for Maintenance or Due to an Unexpected Issue ⚠️"
                    socketio.emit('new_message', {'message': [{'ERROR': message}]})
                    project_services_down_message_sent = True
                    project_restart_message_sent = False
                    print(f"\n{message}\n")

                    if kafka_consumer is not None:
                        kafka_consumer = None

        else:
            server_ping_fail += 1

            if server_ping_fail >= NETWORK_FAIL_CHECK and not connection_failure_message_sent:
                message_queue = []
                messages_to_display = []
                message = "⚠️ Network Issue: Unable to Connect to the Server ⚠️"
                socketio.emit('new_message', {'message': [{'ERROR': message}]})
                connection_failure_message_sent = True
                successful_reconnection_message_sent = False
                project_services_down_message_sent = False
                print(f"\n{message}\n")

                if kafka_consumer is not None:
                    kafka_consumer = None

        if time.time() - last_update_time >= STATUS_THRESHOLD:
            message_queue = []
            messages_to_display = []
            socketio.emit('new_message', {'message': messages_to_display})
            last_update_time = time.time()


kafka_consumer_thread = threading.Thread(target=consume_messages)
kafka_consumer_thread.daemon = True
kafka_consumer_thread.start()


@socketio.on('connect')
def handle_connect():
    global messages_to_display
    emit('new_message', {'message': messages_to_display})


@socketio.on('check_updates')
def handle_check_updates():
    global messages_to_display
    emit('new_message', {'message': messages_to_display})


@app.route('/')
def index():
    global messages_to_display
    return render_template('index.html', message=messages_to_display)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9090)
