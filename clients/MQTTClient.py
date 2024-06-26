import json
import logging
import sys
from time import sleep

from paho.mqtt import reasoncodes
import paho.mqtt.client as mqtt

from clients.BaseClient import BaseClient
from common.consts import *
from models.MQTTConfigData import MQTTConfigurationData


logger = logging.getLogger(__name__)


class MQTTClient(BaseClient):
    def __init__(self):
        super().__init__("MQTT")
        logger.info(f"{MQTT_DEBUG=}")
        if MQTT_DEBUG is True:
            logger.setLevel(logging.DEBUG)
            for handler in logger.handlers:
                handler.setLevel(logging.DEBUG)
            logger.info(f"Set DEBUG level for {__name__}")
        else:
            logger.setLevel(logging.INFO)
            for handler in logger.handlers:
                handler.setLevel(logging.INFO)
            logger.info(f"Set INFO level for {__name__}")
        self._mqtt_config = MQTTConfigurationData()
        self._mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, self._mqtt_config.client_id, clean_session=True)
        self._mqtt_client.user_data_set(self)
        self._mqtt_client.username_pw_set(self._mqtt_config.username, self._mqtt_config.password)

        self._mqtt_client.on_connect = self._on_mqtt_connect
        self._mqtt_client.on_message = self._on_mqtt_message
        self._mqtt_client.on_disconnect = self._on_mqtt_disconnect

    @property
    def topic_command_prefix(self):
        return self._mqtt_config.topic_command_prefix

    @property
    def topic_prefix(self):
        return self._mqtt_config.topic_prefix

    def _connect(self):
        super(MQTTClient, self)._connect()

        config = self._mqtt_config

        while not self.is_connected:
            try:
                logger.info("Trying to connect to MQTT Broker...")

                self._mqtt_client.connect(config.host, int(config.port), 60)
                self._mqtt_client.loop_start()

                sleep(5)

            except Exception as ex:
                exc_type, exc_obj, exc_tb = sys.exc_info()
                error_details = f"error: {ex}, Line: {exc_tb.tb_lineno}"

                logger.error(f"Failed to connect to broker, retry in 60 seconds, {error_details}")

                sleep(60)

    def _event_received(self, data):
        super(MQTTClient, self)._event_received(data)

        topic_suffix = data.get("event")
        payload = data.get("payload")

        topic = f"{self.topic_prefix}/{topic_suffix}"
        logger.debug(f"Publishing MQTT message {topic}: {payload}")

        try:
            self._mqtt_client.publish(topic, json.dumps(payload, indent=4))
        except Exception as ex:
            exc_type, exc_obj, exc_tb = sys.exc_info()

            logger.error(
                f"Failed to publish message, "
                f"Topic: {topic}, Payload: {payload}, "
                f"Error: {ex}, Line: {exc_tb.tb_lineno}"
            )

    @staticmethod
    def _on_mqtt_connect(client, userdata, flags, reason_code: reasoncodes.ReasonCode, properties):
        if reason_code == 0:
            logger.info(f"Connected to MQTT broker with result code: {reason_code}")
            client.subscribe(f"{userdata.topic_command_prefix}#")
            userdata.is_connected = True

        else:
            logger.error(f"Connecting to MQTT Broker failed due to {reason_code}")
            userdata.is_connected = False
            super(MQTTClient, userdata).connect()

    @staticmethod
    def _on_mqtt_message(client, userdata, msg):
        logger.debug(f"MQTT Message received, Topic: {msg.topic}, Payload: {msg.payload}")
        try:
            payload = {}

            if msg.payload is not None:
                data = msg.payload.decode("utf-8")

                if data is not None and len(data) > 0:
                    payload = json.loads(data)

            topic = msg.topic.replace(userdata.topic_command_prefix, "")
            event_data = {
                "topic": topic,
                "payload": payload
            }

            userdata.outgoing_events.put(event_data)
        except Exception as ex:
            exc_type, exc_obj, exc_tb = sys.exc_info()

            logger.error(
                f"Failed to invoke msg ID handler, "
                f"Topic: {msg.topic}, Payload: {msg.payload}, "
                f"Error: {ex}, Line: {exc_tb.tb_lineno}"
            )

    @staticmethod
    def _on_mqtt_disconnect(client, userdata, flags, reason_code, properties):
        # reason_code should now be a string, its __eq__ method still uses ints though.
        logger.warning(f"Disconnected from broker! Reason: {reason_code}")
        userdata.is_connected = False
        super(MQTTClient, userdata).connect()
