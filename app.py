import socket
import threading
import time
import json
import requests
from confluent_kafka import Consumer, TopicPartition, OFFSET_END
from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from custom_logging import feedback_client_logger
from parameters import CONFLUENT_KAFKA_IP_ADDRESS, \
    CONFLUENT_KAFKA_PORT, \
    CONFLUENT_KAFKA_TOPIC, \
    CONFLUENT_KAFKA_PARTITION, \
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
# print(f"\nINITIAL STAGE OF KAFKA CONSUMER: {kafka_consumer}\n")


def ping_server(ip: str, port: int):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
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
            # print(f"\n MESSAGES TO DISPLAY: {messages_to_display}\n")
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
        # print(f"DGX Reachable: {is_dgx_reachable}")
        are_services_running = ping_project_services()
        # print(f"Project Running: {are_services_running}")

        if is_dgx_reachable:
            server_ping_fail = 0
            if not successful_reconnection_message_sent:
                message_queue = []
                messages_to_display = []
                message = "🛜 Network Reconnection Successful 🛜"
                socketio.emit('new_message', {'message': [{'SUCCESS': message}]})
                successful_reconnection_message_sent = True
                connection_failure_message_sent = False
                feedback_client_logger.info("Network Reconnection Successful")
                # print(f"\n{message}\n")

            if are_services_running:
                services_ping_fail = 0
                if not project_restart_message_sent:
                    message_queue = []
                    messages_to_display = []
                    message = "✅ Facial Recognition Attendance System is Getting Started. Please Wait for 2 Minutes ✅"
                    socketio.emit('new_message', {'message': [{'SUCCESS': message}]})
                    feedback_client_logger.info("Facial Recognition Attendance System is Getting Started. Please Wait for 2 Minutes")
                    # print(f"\n{message}\n")
                    time.sleep(2 * 60)

                    message = "Facial Recognition Attendance System Has Been Started. Please Resume Attendance"
                    socketio.emit('new_message', {'message': [{'SUCCESS': message}]})
                    feedback_client_logger.info(message)
                    # print(f"\n{message}\n")

                    project_restart_message_sent = True
                    project_services_down_message_sent = False

                    time.sleep(5)

                if kafka_consumer is None:
                    # Create a Kafka Consumer
                    kafka_consumer = Consumer(kafka_conf)
                    topic_partition = TopicPartition(CONFLUENT_KAFKA_TOPIC, CONFLUENT_KAFKA_PARTITION, OFFSET_END)
                    kafka_consumer.assign([topic_partition])
                    feedback_client_logger.info("Created a fresh kafka consumer")

                # print(f"\nKAFKA CONSUMER AFTER SUCCESSFUL START OF THE PROJECT: {kafka_consumer}\n")

                message_from_kafka = kafka_consumer.poll(0.2)

                if message_from_kafka is None:
                    pass
                    # print("No message received.")
                else:
                    # Check if it is not an error message sent by Kafka
                    # print(f"\nRAW MESSAGE FROM KAFKA: {message_from_kafka}\n")
                    if message_from_kafka.error():
                        # Clear existing messages
                        message_queue = []
                        feedback_client_logger.error(f"Received an error message from kafka: {message_from_kafka.error()}")
                        # while kafka_consumer.poll() is None:
                        #     continue
                    else:
                        decoded_kafka_message = message_from_kafka.value().decode()
                        # print(f"\nMESSAGE RECEIVED FROM KAFKA: {decoded_kafka_message}\n")
                        # Check if coming message is an ERROR message or SUCCESS message
                        if decoded_kafka_message.split(": ")[0].startswith("ERROR") or decoded_kafka_message.split(": ")[0].startswith("SUCCESS"):
                            message_key, message_value = decoded_kafka_message.split(": ")
                            message_queue = []
                            # print(message_queue)
                            message_queue.insert(0, decoded_kafka_message)
                            # print(message_queue)
                            message_data_to_send = {"messages": message_queue}
                            data = json.dumps(message_data_to_send)
                            post_message_queue_and_get_images(data)
                            message_queue = []
                            # print(message_queue)
                        else:
                            if decoded_kafka_message.split(": ")[1] not in message_queue:
                                _, id_ = decoded_kafka_message.split(": ")
                                if len(message_queue) >= DISPLAY_LIST_SIZE:
                                    message_queue.pop()
                                # print(message_queue)
                                message_queue.insert(0, id_)
                                # print(message_queue)
                                message_data_to_send = {"messages": message_queue}
                                data = json.dumps(message_data_to_send)
                                post_message_queue_and_get_images(data)
                                last_update_time = time.time()
            else:
                services_ping_fail += 1

                if services_ping_fail >= NETWORK_FAIL_CHECK and not project_services_down_message_sent:
                    message_queue = []
                    messages_to_display = []
                    message = "⚠️ Facial Recognition System Temporarily Down for Maintenance or Due to an Unexpected Issue ⚠️"
                    socketio.emit('new_message', {'message': [{'ERROR': message}]})
                    project_services_down_message_sent = True
                    project_restart_message_sent = False
                    feedback_client_logger.error("Facial Recognition System Temporarily Down for Maintenance or Due to an Unexpected Issue")
                    # print(f"\n{message}\n")

                    if kafka_consumer is not None:
                        kafka_consumer = None
                        feedback_client_logger.warn("Deleted Kafka Consumer as the facial recognition system shutdown.")

                    # print(f"\nKAFKA CONSUMER STATUS IF PROJECT DOWN: {kafka_consumer}\n")

                    services_ping_fail = 0

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
                feedback_client_logger.error("Network Issue: Unable to Connect to the Server")
                # print(f"\n{message}\n")

                if kafka_consumer is not None:
                    kafka_consumer = None
                    feedback_client_logger.warn("Deleted Kafka Consumer as the server is not reachable.")

                # print(f"\nKAFKA CONSUMER STATUS IF SERVER NOT CONNECTED: {kafka_consumer}\n")

                server_ping_fail = 0

        if time.time() - last_update_time >= STATUS_THRESHOLD:
            message_queue = []
            # print(message_queue)
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
