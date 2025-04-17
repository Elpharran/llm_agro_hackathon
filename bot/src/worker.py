import asyncio
import json
import os
import sys
import traceback
import aio_pika
import pika
from dotenv import load_dotenv
from src.report_builder import ReportBuilder
from src.utils import load_prompt
from src.logger_download import logger

load_dotenv(override=True)

sys_prompt = load_prompt(prompt_path="0. system_prompt.md")
api_keys = os.getenv('MISTRAL_API_KEYS').split(',')
proxy_url = f"socks5://{os.getenv('PROXY_USERNAME')}:{os.getenv('PROXY_PASSWORD')}@{os.getenv('PROXY_IP')}:{os.getenv('PROXY_PORT')}"

workers = {
    "worker_v1": lambda: ReportBuilder(
    config=dict(
        mistral_api_key=api_keys[0],
        proxy_url=None,
        assistant_prompt=sys_prompt,
    )
),
    "worker_v2": lambda: ReportBuilder(
    config=dict(
        mistral_api_key=api_keys[1],
        proxy_url=proxy_url,
        assistant_prompt=sys_prompt,
    )
),
}


def init_rabbitmq():
    connection = pika.BlockingConnection(
        pika.ConnectionParameters("rabbitmq")
    )
    channel = connection.channel()
    channel.queue_declare(queue="query_queue")
    return channel



async def handle_message(message: aio_pika.IncomingMessage, builder, exchange):
    async with message.process():
        query_text = message.body.decode()
        logger.info(f"[Worker] Received message: {query_text}")

        try:
            result = builder.build(query_text)
            logger.info(f"[Worker] Result: {result}")

            if message.reply_to:
                await exchange.publish(
                    aio_pika.Message(
                        body=json.dumps(result, ensure_ascii=False).encode('utf-8'),
                        correlation_id=message.correlation_id,
                    ),
                    routing_key=message.reply_to,
                )
        except Exception as e:
            logger.info(f"[Worker] Error processing message: {e}")
            logger.info(traceback.format_exc())


async def start_worker(worker_name):
    logger.info((f"[Worker] Starting worker: {worker_name}"))
    builder = workers[worker_name]()

    try:
        connection = await aio_pika.connect_robust("amqp://guest:guest@rabbitmq/")
        logger.info("[Worker] Connected to RabbitMQ.")
    except Exception as e:
        logger.info(f"[Worker] Failed to connect to RabbitMQ: {e}")
        return
    try:
        channel = await connection.channel()
        queue = await channel.declare_queue("query_queue", durable=True)
        exchange = aio_pika.Exchange(name="", type="direct", channel=channel)
        logger.info(f"[Worker] Queue declared: {queue.name}")
    except Exception as e:
        logger.info(f"[Worker] Error declaring queue: {e}")
        return

    logger.info(f"[Worker] Listening for messages with {worker_name}...")
    
    await queue.consume(lambda msg: handle_message(msg, builder, exchange), no_ack=False)
    
    logger.info("[Worker] Consumer set up. Waiting for messages...")

    await asyncio.Future()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        logger.info("Usage: python worker.py <worker_name>")
        sys.exit(1)

    worker_name = sys.argv[1]
    try:
        asyncio.run(start_worker(worker_name))
    except KeyboardInterrupt:
        logger.info("\n[Worker] Shutting down...")
    except Exception as e:
        logger.info(f"[Worker] Exception: {e}")