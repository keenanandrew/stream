import argparse # something to do with command line arguments
import json # handling json objects
import random # random number generation
from datetime import datetime
from uuid import uuid4 # unique identifiers

import psycopg2 # adaptor for postgres
from confluent_kafka import Producer # kafka!
from faker import Faker # module for creating fake data

fake = Faker() # initialise a Faker object


# Generate user data
def gen_user_data(num_user_records: int) -> None: # indicates the function doesn't return a value
    for id in range(num_user_records):
        # the database connection
        conn = psycopg2.connect(
            dbname="postgres",
            user="postgres",
            password="postgres",
            host="postgres",
        )
        curr = conn.cursor()
        curr.execute(
            """INSERT INTO commerce.users
             (id, username, password) VALUES (%s, %s, %s)""",
            (id, fake.user_name(), fake.password()),
        )
        curr.execute(
            """INSERT INTO commerce.products
             (id, name, description, price) VALUES (%s, %s, %s, %s)""",
            (id, fake.name(), fake.text(), fake.random_int(min=1, max=100)),
        )
        conn.commit()

        # update 10 % of the time
        if random.randint(1, 100) >= 90:
            curr.execute(
                "UPDATE commerce.users SET username = %s WHERE id = %s",
                (fake.user_name(), id),
            )
            curr.execute(
                "UPDATE commerce.products SET name = %s WHERE id = %s",
                (fake.name(), id),
            )
        conn.commit()
        curr.close()
    return


# Stream clicks and checkouts data


# Generate a random user agent string
def random_user_agent():
    # user_agent must be something predefined in Faker
    # 'fake' is the Faker object created earlier
    return fake.user_agent()


# Generate a random IP address
def random_ip():
    return fake.ipv4()


# Generate a click event with the current datetime_occured
def generate_click_event(user_id, product_id=None):
    click_id = str(uuid4())
    product_id = product_id or str(uuid4())
    product = fake.word()
    price = fake.pyfloat(left_digits=2, right_digits=2, positive=True)
    url = fake.uri()
    user_agent = random_user_agent()
    ip_address = random_ip()
    datetime_occured = datetime.now()

    # looks like a simple way to define a json object

    click_event = {
        "click_id": click_id,
        "user_id": user_id,
        "product_id": product_id,
        "product": product,
        "price": price,
        "url": url,
        "user_agent": user_agent,
        "ip_address": ip_address,
        "datetime_occured": datetime_occured.strftime("%Y-%m-%d %H:%M:%S.%f")[
            :-3
        ],
    }

    return click_event


# Generate a checkout event with the current datetime_occured
def generate_checkout_event(user_id, product_id):
    payment_method = fake.credit_card_provider()
    total_amount = fake.pyfloat(left_digits=3, right_digits=2, positive=True)
    shipping_address = fake.address()
    billing_address = fake.address()
    user_agent = random_user_agent()
    ip_address = random_ip()
    datetime_occured = datetime.now()

    checkout_event = {
        "checkout_id": str(uuid4()),
        "user_id": user_id,
        "product_id": product_id,
        "payment_method": payment_method,
        "total_amount": total_amount,
        "shipping_address": shipping_address,
        "billing_address": billing_address,
        "user_agent": user_agent,
        "ip_address": ip_address,
        "datetime_occured": datetime_occured.strftime("%Y-%m-%d %H:%M:%S.%f")[
            :-3
        ],
    }

    return checkout_event


# Function to push the events to a Kafka topic

# ok this is the bit that's new to me
# Producer is some submodule of the kafka library
#

def push_to_kafka(event, topic):
    producer = Producer({'bootstrap.servers': 'kafka:9092'})
    producer.produce(topic, json.dumps(event).encode('utf-8'))
    # flush - checks that previously sent messages have been' completed'
    producer.flush()


def gen_clickstream_data(num_click_records: int) -> None:
    for _ in range(num_click_records):
        # the _ is a convention for a variable that isn't actually used in the block
        user_id = random.randint(1, 100)
        click_event = generate_click_event(user_id) # the json objects are created here
        # here's the push_to_kafka function
        push_to_kafka(click_event, 'clicks') # sent to the 'clicks' topic

        # simulate multiple clicks & checkouts 50% of the time
        while random.randint(1, 100) >= 50:
            # generate_click_event is the function that makes a json object
            click_event = generate_click_event(
                user_id, click_event['product_id']
            )
            push_to_kafka(click_event, 'clicks')

            push_to_kafka(
                generate_checkout_event(
                    click_event["user_id"], click_event["product_id"]
                ),
                'checkouts',
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-nu",
        "--num_user_records",
        type=int,
        help="Number of user records to generate",
        default=100,
    )
    parser.add_argument(
        "-nc",
        "--num_click_records",
        type=int,
        help="Number of click records to generate",
        default=100000000, # wow
    )
    args = parser.parse_args()
    gen_user_data(args.num_user_records)
    gen_clickstream_data(args.num_click_records)
