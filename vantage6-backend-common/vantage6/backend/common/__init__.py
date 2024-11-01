""" Common functionality for the vantage6 server and algorithm store.
"""

# make sure the version is available
from vantage6.backend.common._version import __version__  # noqa: F401

from vantage6.backend.common.globals import DEFAULT_API_PATH


def get_server_url(config: dict, server_url_from_request: str | None = None) -> str:
    """ "
    Get the server url from the server configuration, or from the request
    data if it is not present in the configuration.

    Parameters
    ----------
    config : dict
        Server configuration
    server_url_from_request : str | None
        Server url from the request data.

    Returns
    -------
    str | None
        The server url
    """
    server_url = config.get("server_url", server_url_from_request)
    # make sure that the server url ends with the api path
    api_path = config.get("api_path", DEFAULT_API_PATH)
    if server_url and not server_url.endswith(api_path):
        server_url = server_url + api_path
    return server_url
