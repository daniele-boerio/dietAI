"""Svuota la lista della spesa corrente.

Uso: python -m app.clear_shopping_list
"""

from .database import SessionLocal
from .models import ShoppingList, ShoppingListItem, WeekPlan


def main():
    db = SessionLocal()
    try:
        # Trova la settimana corrente (quella non archiviata più recente)
        current_week = (
            db.query(WeekPlan)
            .filter(WeekPlan.status != 'archived')
            .order_by(WeekPlan.week_start_date.desc())
            .first()
        )
        
        if not current_week:
            print("❌ Nessuna settimana corrente trovata.")
            return
        
        # La settimana deve avere una lista della spesa
        if not current_week.shopping_list:
            print("❌ Nessuna lista della spesa associata alla settimana.")
            return
        
        # Conta gli articoli prima
        count = (
            db.query(ShoppingListItem)
            .filter(ShoppingListItem.shopping_list_id == current_week.shopping_list.id)
            .count()
        )
        
        if count == 0:
            print("✓ La lista della spesa è già vuota.")
            return
        
        # Cancella
        db.query(ShoppingListItem).filter(
            ShoppingListItem.shopping_list_id == current_week.shopping_list.id
        ).delete()
        
        # Azzera il costo stimato
        current_week.shopping_list.estimated_cost = None
        
        db.commit()
        print(f"✓ Rimossi {count} articoli dalla lista della spesa.")
    
    except Exception as e:
        print(f"❌ Errore: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
