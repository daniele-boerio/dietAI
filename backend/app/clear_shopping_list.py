"""Svuota la lista della spesa corrente.

Uso: python -m app.clear_shopping_list
"""

from .database import SessionLocal
from .models import ShoppingList, ShoppingListItem, WeekPlan


def main():
    db = SessionLocal()
    try:
        # Debug: vedi tutte le settimane
        all_weeks = db.query(WeekPlan).order_by(WeekPlan.week_start_date.desc()).all()
        print(f"Debug: {len(all_weeks)} settimane totali nel DB")
        for w in all_weeks[:3]:
            print(f"  - {w.week_start_date} (status: {w.status})")
        
        # Cerca la lista della spesa più recente direttamente
        shopping_list = (
            db.query(ShoppingList)
            .join(WeekPlan, ShoppingList.week_plan_id == WeekPlan.id)
            .filter(WeekPlan.status != 'archived')
            .order_by(WeekPlan.week_start_date.desc())
            .first()
        )
        
        if not shopping_list:
            # Se non la trovi non archiviata, cerca la più recente in assoluto
            shopping_list = (
                db.query(ShoppingList)
                .order_by(ShoppingList.created_at.desc())
                .first()
            )
            if not shopping_list:
                print("❌ Nessuna lista della spesa trovata nel database.")
                return
            print(f"Debug: trovata lista della spesa (creata il {shopping_list.created_at})")
        
        # Conta gli articoli
        count = (
            db.query(ShoppingListItem)
            .filter(ShoppingListItem.shopping_list_id == shopping_list.id)
            .count()
        )
        
        if count == 0:
            print("✓ La lista della spesa è già vuota.")
            return
        
        # Cancella
        db.query(ShoppingListItem).filter(
            ShoppingListItem.shopping_list_id == shopping_list.id
        ).delete()
        
        # Azzera il costo stimato
        shopping_list.estimated_cost = None
        
        db.commit()
        print(f"✓ Rimossi {count} articoli dalla lista della spesa.")
    
    except Exception as e:
        print(f"❌ Errore: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    main()
