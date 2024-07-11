import subprocess
import click

from vantage6.cli.context.algorithm_store import AlgorithmStoreContext
from vantage6.cli.context.server import ServerContext
from vantage6.cli.context.node import NodeContext
from vantage6.cli.common.decorator import click_insert_context
from vantage6.cli.server.start import cli_server_start
from vantage6.common.globals import InstanceType
from vantage6.client import Client


@click.command()
@click_insert_context(type_=InstanceType.SERVER)
@click.option(
    "--server-image", type=str, default=None, help="Server Docker image to use"
)
@click.option("--node-image", type=str, default=None, help="Node Docker image to use")
@click.option(
    "--store-image", type=str, default=None, help="Algorithm Store Docker image to use"
)
@click.pass_context
def start_demo_network(
    click_ctx: click.Context,
    ctx: ServerContext,
    server_image: str,
    node_image: str,
    store_image: str,
) -> None:
    """Starts running a demo-network.

    Select a server configuration to run its demo network. You should choose a
    server configuration that you created earlier for a demo network. If you
    have not created a demo network, you can run `vdev create-demo-network` to
    create one.
    """
    # run the server
    click_ctx.invoke(
        cli_server_start,
        ctx=ctx,
        ip=None,
        port=None,
        image=server_image,
        start_ui=True,
        ui_port=None,
        start_rabbitmq=False,
        rabbitmq_image=None,
        keep=True,
        mount_src="",
        attach=False,
    )

    # run the store
    cmd = ["v6", "algorithm-store", "start", "--name", f"{ctx.name}_store"]
    if store_image:
        cmd.extend(["--image", store_image])
    subprocess.run(cmd)

    # run all nodes that belong to this server
    configs, _ = NodeContext.available_configurations(system_folders=False)
    node_names = [
        config.name for config in configs if config.name.startswith(f"{ctx.name}_node_")
    ]
    for name in node_names:
        cmd = ["v6", "node", "start", "--name", name]
        if node_image:
            cmd.extend(["--image", node_image])
        subprocess.run(cmd)

    # now that both server and store have been started, couple them
    store_ctxs, _ = AlgorithmStoreContext.available_configurations(system_folders=True)
    store_ctx = [c for c in store_ctxs if c.name == f"{ctx.name}_store"][0]
    client = Client(
        "http://localhost",
        ctx.config["port"],
        ctx.config["api_path"],
        log_level="warn",
    )
    # TODO these credentials are hardcoded and may change if changed elsewhere. Link
    # them together so that they are guaranteed to be the same.
    USERNAME = "org_1-admin"
    client.authenticate(USERNAME, "password")
    existing_stores = client.store.list().get("data", [])
    if not existing_stores:
        store = client.store.create(
            # TODO get store port
            algorithm_store_url=f"http://localhost:{store_ctx.config['port']}",
            name="local store",
            all_collaborations=True,
            force=True,  # required to link localhost store
        )
        client.store.set(store["id"])
        # register user as store admin
        client.store.user.register(USERNAME, [1])
