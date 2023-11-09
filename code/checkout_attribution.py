# here we use Apache Table API,
# which specialises in stream and batch processing
# it's a superset of SQL, so it should be easy
# enough to comprehend


from dataclasses import asdict, dataclass, field
from typing import List, Tuple  # for type hinting? not sure why necessary

from jinja2 import Environment  # a template engine, as seen in dbt
from jinja2 import FileSystemLoader
from pyflink.datastream import (
    StreamExecutionEnvironment,
)  # for setting up streaming
from pyflink.table import StreamTableEnvironment  # for setting up Table

# dependency jars to read data from kafka, and connect to postgres
# it stands for Java ARchive

REQUIRED_JARS = [
    "file:///opt/flink/flink-sql-connector-kafka-1.17.0.jar",
    "file:///opt/flink/flink-connector-jdbc-3.0.0-1.16.jar",
    "file:///opt/flink/postgresql-42.6.0.jar",
]


@dataclass(frozen=True)
class StreamJobConfig:
    job_name: str = 'checkout-attribution-job'
    jars: List[str] = field(default_factory=lambda: REQUIRED_JARS)
    checkpoint_interval: int = 10
    checkpoint_pause: int = 5
    checkpoint_timeout: int = 5
    parallelism: int = 2


@dataclass(frozen=True)
class KafkaConfig:
    connector: str = 'kafka'
    bootstrap_servers: str = 'kafka:9092'
    scan_stratup_mode: str = 'earliest-offset'
    consumer_group_id: str = 'flink-consumer-group-1'


@dataclass(frozen=True)
class ClickTopicConfig(KafkaConfig):
    topic: str = 'clicks'
    format: str = 'json'


@dataclass(frozen=True)
class CheckoutTopicConfig(KafkaConfig):
    topic: str = 'checkouts'
    format: str = 'json'


@dataclass(frozen=True)
class ApplicationDatabaseConfig:
    connector: str = 'jdbc'
    url: str = 'jdbc:postgresql://postgres:5432/postgres'
    username: str = 'postgres'
    password: str = 'postgres'
    driver: str = 'org.postgresql.Driver'


@dataclass(frozen=True)
class ApplicationUsersTableConfig(ApplicationDatabaseConfig):
    table_name: str = 'commerce.users'


@dataclass(frozen=True)
class ApplicationAttributedCheckoutsTableConfig(ApplicationDatabaseConfig):
    table_name: str = 'commerce.attributed_checkouts'


def get_execution_environment(
    config: StreamJobConfig,
) -> Tuple[StreamExecutionEnvironment, StreamTableEnvironment]:
    s_env = StreamExecutionEnvironment.get_execution_environment()
    for jar in config.jars:
        s_env.add_jars(jar)
    # start a checkpoint every 10,000 ms (10 s)
    s_env.enable_checkpointing(config.checkpoint_interval * 1000)
    # make sure 5000 ms (5 s) of progress happen between checkpoints
    s_env.get_checkpoint_config().set_min_pause_between_checkpoints(
        config.checkpoint_pause * 1000
    )
    # checkpoints have to complete within 5 minute, or are discarded
    s_env.get_checkpoint_config().set_checkpoint_timeout(
        config.checkpoint_timeout * 1000
    )
    execution_config = s_env.get_config()
    execution_config.set_parallelism(config.parallelism)
    t_env = StreamTableEnvironment.create(s_env)
    job_config = t_env.get_config().get_configuration()
    job_config.set_string("pipeline.name", config.job_name)
    return s_env, t_env


def get_sql_query(
    # this function is called several times
    # by the below function
    # it takes a string, then returns the sql file
    # located at source/'string'
    # and adds some other kafka-esque information
    # that I don't quite understand yet
    #
    entity: str,
    type: str = 'source',
    template_env: Environment = Environment(loader=FileSystemLoader("code/")),
) -> str:
    config_map = {
        'clicks': ClickTopicConfig(),
        'checkouts': CheckoutTopicConfig(),
        'users': ApplicationUsersTableConfig(),
        'attributed_checkouts': ApplicationUsersTableConfig(),
        'attribute_checkouts': ApplicationAttributedCheckoutsTableConfig(),
    }

    return template_env.get_template(f"{type}/{entity}.sql").render(
        asdict(config_map.get(entity))
    )


def run_checkout_attribution_job(
    t_env: StreamTableEnvironment,
    get_sql_query=get_sql_query,
) -> None:
    # Create Source DDLs
    # DDL = Data Definition Language
    t_env.execute_sql(get_sql_query('clicks'))
    # goes to the sql query 'clicks' and executes it
    # creates the 'clicks' table

    t_env.execute_sql(get_sql_query('checkouts'))
    # goes to the sql query 'checkouts' and executes it
    # this query is stored elsewhere
    # for reusability / editability
    # it CREATEs a TABLE, checkouts,
    # with cols for the various fake data to be generated

    t_env.execute_sql(get_sql_query('users'))
    # goes to the sql query 'users' and executes it
    # creates the 'users' table

    # Create Sink DDL
    # this executes two SQL queries
    # It has two arguments as it's in a subfolder
    t_env.execute_sql(get_sql_query('attributed_checkouts', 'sink'))

    # Run processing query
    # Also gets two args due to being in a different folder
    stmt_set = t_env.create_statement_set()
    stmt_set.add_insert_sql(get_sql_query('attribute_checkouts', 'process'))

    checkout_attribution_job = stmt_set.execute()
    print(
        f"""
        Async attributed checkouts sink job
         status: {checkout_attribution_job.get_job_client().get_job_status()}
        """
    )


if __name__ == '__main__':
    _, t_env = get_execution_environment(StreamJobConfig())
    run_checkout_attribution_job(t_env)
