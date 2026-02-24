from pydantic import BaseModel, Field
from datetime import datetime


class Holding(BaseModel):
    symbol: str
    name: str | None = None
    quantity: float
    market_price: float = Field(alias="marketPrice", default=0)
    value_in_base_currency: float = Field(alias="valueInBaseCurrency", default=0)
    allocation_in_percentage: float = Field(alias="allocationInPercentage", default=0)
    currency: str | None = None
    asset_class: str | None = Field(alias="assetClass", default=None)
    asset_sub_class: str | None = Field(alias="assetSubClass", default=None)
    data_source: str | None = Field(alias="dataSource", default=None)

    model_config = {"populate_by_name": True}


class Order(BaseModel):
    id: str
    symbol: str | None = None
    type: str  # BUY, SELL, DIVIDEND, FEE, INTEREST
    quantity: float
    unit_price: float = Field(alias="unitPrice", default=0)
    fee: float = 0
    currency: str | None = None
    date: datetime
    account_id: str | None = Field(alias="accountId", default=None)

    model_config = {"populate_by_name": True}


class SymbolSearchItem(BaseModel):
    symbol: str
    name: str | None = None
    data_source: str = Field(alias="dataSource")
    currency: str | None = None
    asset_class: str | None = Field(alias="assetClass", default=None)
    asset_sub_class: str | None = Field(alias="assetSubClass", default=None)

    model_config = {"populate_by_name": True}


class SymbolSearchResult(BaseModel):
    items: list[SymbolSearchItem] = Field(default_factory=list)


class PortfolioHoldings(BaseModel):
    holdings: list[Holding] = Field(default_factory=list)
