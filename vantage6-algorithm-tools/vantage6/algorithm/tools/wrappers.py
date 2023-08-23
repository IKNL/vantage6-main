"""
This module contains algorithm wrappers. These wrappers are used to provide
different data adapters to the algorithms. This way we ony need to write the
algorithm once and can use it with different data adapters.

Currently the following wrappers are available:
    - ``DockerWrapper`` (= ``CSVWrapper``)
    - ``SparqlDockerWrapper``
    - ``ParquetWrapper``
    - ``SQLWrapper``
    - ``OMOPWrapper``
    - ``ExcelWrapper``

When writing the Docker file for the algorithm, the correct wrapper will
automatically be selected based on the database type. The database type is set
by the vantage6 node based on its configuration file.
"""
from __future__ import annotations
import io
import pandas

from abc import ABC, abstractmethod
from SPARQLWrapper import SPARQLWrapper, CSV

from vantage6.algorithm.tools.util import info, error

_SPARQL_RETURN_FORMAT = CSV


def select_wrapper(database_type: str) -> WrapperBase | None:
    """
    Select the correct wrapper based on the database type.

    Parameters
    ----------
    database_type : str
        The database type to select the wrapper for.

    Returns
    -------
    derivative of WrapperBase | None
        The wrapper for the specified database type. None if the database type
        is not supported by a wrapper.
    """
    if database_type == "csv":
        return CSVWrapper()
    elif database_type == "excel":
        return ExcelWrapper()
    elif database_type == "sparql":
        return SparqlDockerWrapper()
    elif database_type == "parquet":
        return ParquetWrapper()
    elif database_type == "sql":
        return SQLWrapper()
    elif database_type == "omop":
        return OMOPWrapper()
    else:
        return None


class WrapperBase(ABC):
    @staticmethod
    @abstractmethod
    def load_data(database_uri: str, **kwargs):
        """
        Load the local privacy-sensitive data from the database.

        Parameters
        ----------
        database_uri : str
            URI of the database to read
        **kwargs
            Additional parameters that may be required to read the database
        """
        pass


class CSVWrapper(WrapperBase):
    @staticmethod
    def load_data(database_uri: str) -> pandas.DataFrame:
        """
        Load the local privacy-sensitive data from the database.

        Parameters
        ----------
        database_uri : str
            URI of the csv file, supplied by te node

        Returns
        -------
        pandas.DataFrame
            The data from the csv file
        """
        return pandas.read_csv(database_uri)


class ExcelWrapper(WrapperBase):
    @staticmethod
    def load_data(database_uri: str, sheet_name: str = 0) -> pandas.DataFrame:
        """
        Load the local privacy-sensitive data from the database.

        Parameters
        ----------
        database_uri : str
            URI of the excel file, supplied by te node
        sheet_name : str, optional
            The worksheet to read, which is passed to pandas.read_excel. By
            default, the first sheet '0' is read

        Returns
        -------
        pandas.DataFrame
            The data from the excel file
        """
        info(f"Reading sheet '{sheet_name}' from excel file")
        return pandas.read_excel(database_uri, sheet_name=sheet_name)


class SparqlDockerWrapper(WrapperBase):
    @staticmethod
    def load_data(database_uri: str, query: str) -> pandas.DataFrame:
        """
        Load the local privacy-sensitive data from the database.

        Parameters
        ----------
        database_uri : str
            URI of the triplestore, supplied by te node
        input_data : dict
            Can contain a 'query', to retrieve the data from the triplestore

        Returns
        -------
        pandas.DataFrame
            The data from the triplestore
        """
        return SparqlDockerWrapper._query_triplestore(database_uri, query)

    @staticmethod
    def _query_triplestore(endpoint: str, query: str) -> pandas.DataFrame:
        """
        Send a query to a triplestore and return the result as a pandas
        DataFrame.

        Parameters
        ----------
        endpoint : str
            URI of the triplestore
        query : str
            The query to send to the triplestore

        Returns
        -------
        pandas.DataFrame
            The result of the query
        """
        sparql = SPARQLWrapper(endpoint, returnFormat=_SPARQL_RETURN_FORMAT)
        sparql.setQuery(query)

        result = sparql.query().convert().decode()

        return pandas.read_csv(io.StringIO(result))


class ParquetWrapper(WrapperBase):
    @staticmethod
    def load_data(database_uri: str) -> pandas.DataFrame:
        """
        Load the local privacy-sensitive data from the database.

        Parameters
        ----------
        database_uri : str
            URI of the parquet file, supplied by te node

        Returns
        -------
        pandas.DataFrame
            The data from the parquet file
        """
        return pandas.read_parquet(database_uri)


class SQLWrapper(WrapperBase):
    @staticmethod
    def load_data(database_uri: str, query: str) -> pandas.DataFrame:
        """
        Load the local privacy-sensitive data from the database.

        Parameters
        ----------
        database_uri : str
            URI of the sql database, supplied by te node
        query : str
            The query to send to the database

        Returns
        -------
        pandas.DataFrame
            The data from the database
        """
        return pandas.read_sql(database_uri, query)


class OMOPWrapper(WrapperBase):
    @staticmethod
    def load_data(database_uri: str, query: str) -> pandas.DataFrame:
        """
        Load the local privacy-sensitive data from the database.

        Parameters
        ----------
        database_uri : str
            URI of the OMOP database, supplied by te node
        query: str
            The query to send to the database

        Returns
        -------
        pandas.DataFrame
            The data from the database
        """
        # TODO: replace query by OMOP json and convert to SQL
        return pandas.read_sql(database_uri, query)
