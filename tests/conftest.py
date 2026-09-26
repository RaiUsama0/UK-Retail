import pandas as pd
import pytest

from ecommerce_analytics.schema import SHEET_NAME

# A small, hand-crafted dataset with deliberately known statistics:
# - 8 rows, but row index 7 is an exact duplicate of row index 0 -> 1 duplicate row
# - 7 distinct InvoiceNo values (duplicate row reuses InvoiceNo 536001)
# - 5 distinct StockCode values, 3 distinct non-null CustomerID values, 4 countries
# - CustomerID missing on 2 rows, Description missing on 1 row
# - 1 cancellation (InvoiceNo starts with 'C', negative quantity)
# - 1 "potential return": negative quantity but NOT a cancellation-prefixed invoice
# - 1 row with UnitPrice == 0
_RECORDS = [
    # InvoiceNo, StockCode, Description, Quantity, InvoiceDate, UnitPrice, CustomerID, Country
    ("536001", "10001", "WIDGET A", 6, "2011-01-01", 2.5, 1001.0, "United Kingdom"),
    ("536002", "10002", "WIDGET B", 3, "2011-01-02", 5.0, 1002.0, "France"),
    ("536003", "10001", "WIDGET A", 2, "2011-01-03", 2.5, 1001.0, "United Kingdom"),
    ("C536004", "10002", "WIDGET B", -1, "2011-01-04", 5.0, 1002.0, "France"),
    ("536005", "10003", None, 1, "2011-01-05", 0.0, None, "United Kingdom"),
    ("536006", "10004", "WIDGET D", -2, "2011-01-06", 3.0, 1003.0, "Germany"),
    ("536007", "10005", "WIDGET E", 4, "2011-01-07", 1.5, None, "Spain"),
    ("536001", "10001", "WIDGET A", 6, "2011-01-01", 2.5, 1001.0, "United Kingdom"),  # dup of row 0
]

_COLUMNS = [
    "InvoiceNo",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "UnitPrice",
    "CustomerID",
    "Country",
]


@pytest.fixture
def sample_df() -> pd.DataFrame:
    df = pd.DataFrame(_RECORDS, columns=_COLUMNS)
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    return df


@pytest.fixture
def write_sample_xlsx(sample_df, tmp_path):
    """Returns a function that writes the sample dataframe (or a custom one) to an
    .xlsx file at the given path, using the correct sheet name."""

    def _write(path, df: pd.DataFrame | None = None):
        path.parent.mkdir(parents=True, exist_ok=True)
        (df if df is not None else sample_df).to_excel(path, sheet_name=SHEET_NAME, index=False)
        return path

    return _write
