"""
This module contains several preprocessing functions that may be used to
prepare the data for the algorithm.
"""

import pandas as pd


def select_rows(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """
    Select rows from the data based on a query. It uses the pandas.DataFrame.query
    function to filter the data. See the documentation of that function for more
    information on the query syntax.

    Parameters
    ----------
    df : pandas.DataFrame
        The data to filter.
    query : str
        The query to filter on.

    Returns
    -------
    pandas.DataFrame
        The filtered data.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame(
    ...     {
    ...         "a": [1, 2, 3, 4, 5],
    ...         "b": [6, 7, 8, 9, 10],
    ...         "c": [11, 12, 13, 14, 15],
    ...     }
    ... )
    >>> df
       a   b   c
    0  1   6  11
    1  2   7  12
    2  3   8  13
    3  4   9  14
    4  5  10  15

    >>> select_rows(df, "a > 2")
       a   b   c
    2  3   8  13
    3  4   9  14
    4  5  10  15

    >>> select_rows(df, "a > 2 and b < 10")
       a  b   c
    2  3  8  13
    3  4  9  14

    >>> select_rows(df, "a > 2 or c < 12")
       a   b   c
    0  1   6  11
    2  3   8  13
    3  4   9  14
    4  5  10  15

    >>> select_rows(df, "2 * a + b > c")
       a   b   c
    2  3   8  13
    3  4   9  14
    4  5  10  15

    for more examples, see the documentation of pandas.DataFrame.query
    """
    return df.query(query)


def filter_range(
    df: pd.DataFrame,
    column: str,
    min_: float = None,
    max_: float = None,
    include_min: bool = False,
    include_max: bool = False,
) -> pd.DataFrame:
    """
    Filter the data based on a minimum and/or maximum value.

    Parameters
    ----------
    df : pandas.DataFrame
        The data to filter.
    column : str
        The column to filter on.
    min_ : float, optional
        The minimum value to filter on, by default None.
    max_ : float, optional
        The maximum value to filter on, by default None.
    include_min : bool, optional
        Whether to include the minimum value, by default False.
    include_max : bool, optional
        Whether to include the maximum value, by default False.

    Returns
    -------
    pandas.DataFrame
        The filtered data.
    """
    if column is None:
        column = df.index.name

    if min_ is not None:
        if include_min:
            df = df[df[column] >= min_]
        else:
            df = df[df[column] > min_]

    if max_ is not None:
        if include_max:
            df = df[df[column] <= max_]
        else:
            df = df[df[column] < max_]

    return df


def select_columns(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    """
    Select columns from the data.

    Parameters
    ----------
    df : pandas.DataFrame
        The data to filter.
    columns : list
        A list of names of the columns to keep in the provided order.

    Returns
    -------
    pandas.DataFrame
        The filtered data.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame(
    ...     {
    ...         "a": [1, 2, 3, 4, 5],
    ...         "b": [6, 7, 8, 9, 10],
    ...         "c": [11, 12, 13, 14, 15],
    ...     }
    ... )
    >>> df
       a   b   c
    0  1   6  11
    1  2   7  12
    2  3   8  13
    3  4   9  14
    4  5  10  15

    >>> select_columns(df, ["a", "c"])
       a   c
    0  1  11
    1  2  12
    2  3  13
    3  4  14
    4  5  15

    >>> select_columns(df, ["c", "a"])
        c  a
    0  11  1
    1  12  2
    2  13  3
    3  14  4
    4  15  5

    """
    return df[columns]


def select_columns_by_index(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    """
    Select columns from the data.

    Parameters
    ----------
    df : pandas.DataFrame
        The data to filter.
    columns : list
        A list of indices of the columns to keep in the provided order.

    Returns
    -------
    pandas.DataFrame
        The filtered data.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame(
    ...     {
    ...         "a": [1, 2, 3, 4, 5],
    ...         "b": [6, 7, 8, 9, 10],
    ...         "c": [11, 12, 13, 14, 15],
    ...     }
    ... )
    >>> df
       a   b   c
    0  1   6  11
    1  2   7  12
    2  3   8  13
    3  4   9  14
    4  5  10  15

    >>> select_columns_by_index(df, [0, 2])
       a   c
    0  1  11
    1  2  12
    2  3  13
    3  4  14
    4  5  15

    >>> select_columns_by_index(df, [2, 0])
        c  a
    0  11  1
    1  12  2
    2  13  3
    3  14  4
    4  15  5

    """
    return df.iloc[:, columns]


def drop_columns(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    """
    Drop columns from the data.

    Parameters
    ----------
    df : pandas.DataFrame
        The data to filter.
    columns : list
        A list of names of the columns to drop.

    Returns
    -------
    pandas.DataFrame
        The filtered data.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame(
    ...     {
    ...         "a": [1, 2, 3, 4, 5],
    ...         "b": [6, 7, 8, 9, 10],
    ...         "c": [11, 12, 13, 14, 15],
    ...     }
    ... )
    >>> df
       a   b   c
    0  1   6  11
    1  2   7  12
    2  3   8  13
    3  4   9  14
    4  5  10  15

    >>> drop_columns(df, ["a", "c"])
        b
    0   6
    1   7
    2   8
    3   9
    4  10

    """

    return df.drop(columns, axis=1)


def drop_columns_by_index(df: pd.DataFrame, columns: list) -> pd.DataFrame:
    """
    Drop columns from the data.

    Parameters
    ----------
    df : pandas.DataFrame
        The data to filter.
    columns : list
        A list of indices of the columns to drop.

    Returns
    -------
    pandas.DataFrame
        The filtered data.

    Examples
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame(
    ...     {
    ...         "a": [1, 2, 3, 4, 5],
    ...         "b": [6, 7, 8, 9, 10],
    ...         "c": [11, 12, 13, 14, 15],
    ...     }
    ... )
    >>> df
       a   b   c
    0  1   6  11
    1  2   7  12
    2  3   8  13
    3  4   9  14
    4  5  10  15
    >>> drop_columns_by_index(df, [0, 2])
        b
    0   6
    1   7
    2   8
    3   9
    4  10

    >>> drop_columns_by_index(df, [-1])
       a   b
    0  1   6
    1  2   7
    2  3   8
    3  4   9
    4  5  10

    """

    return df.drop(df.columns[columns], axis=1)


# TODO delete later on
def dummy_preprocess(df: pd.DataFrame) -> pd.DataFrame:
    """
    Dummy preprocessing function that does nothing.

    Parameters
    ----------
    df : pandas.DataFrame
        The data to preprocess.

    Returns
    -------
    pandas.DataFrame
        The preprocessed data.
    """
    return df
