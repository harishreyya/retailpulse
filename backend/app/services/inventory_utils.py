from app.models import StockStatus


def compute_stock_status(available_stock: int, reorder_level: int) -> StockStatus:
    """
    Derive stock status from available quantity vs. reorder level.

    - available_stock <= 0            -> OUT_OF_STOCK
    - 0 < available_stock <= reorder  -> LOW_STOCK
    - available_stock > reorder_level -> IN_STOCK
    """
    if available_stock <= 0:
        return StockStatus.OUT_OF_STOCK
    if available_stock <= reorder_level:
        return StockStatus.LOW_STOCK
    return StockStatus.IN_STOCK