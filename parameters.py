# Project Services
DGX_IP_ADDRESS = "192.168.12.1"

PROJECT_SERVICES_PORT = [
    6385,       # InsightFace
    19530,      # Milvus
    9092,       # Kafka
    6381,       # Redis
    20001,      # Database-Controller
    20012,      # Kafka-Message-Controller
    20013       # Display-Image-Server
]

# Kafka IP and Port
CONFLUENT_KAFKA_IP_ADDRESS = DGX_IP_ADDRESS
CONFLUENT_KAFKA_PORT = 9092

# Kafka topic for messages
CONFLUENT_KAFKA_TOPIC = 'feedback_messages_topic_for_tapo-cam-1'

# Number of names to be displayed at once
DISPLAY_LIST_SIZE = 4

# Number of times to check for connection failure
NETWORK_FAIL_CHECKS = 5

# Message Retention time on Screen
STATUS_THRESHOLD = 15

# Image Server Address
IMAGE_SERVER_ADDRESS = "http://192.168.12.1:20013/post_images"
