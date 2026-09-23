from app import app, Expense, TzsExpense, Income, TzsIncome

with app.app_context():
    # Check NSSF entries
    nssf_exp = Expense.query.filter_by(category='NSSF').all()
    nssf_tzs = TzsExpense.query.filter_by(category='NSSF').all()
    print(f'Expense.NSSF count: {len(nssf_exp)}')
    print(f'TzsExpense.NSSF count: {len(nssf_tzs)}')
    for e in nssf_exp[:3]:
        print(f'  Expense: id={e.id}, date={e.date}, cat={e.category}, amt={e.amount}')
    for e in nssf_tzs[:3]:
        print(f'  TzsExpense: id={e.id}, date={e.date}, cat={e.category}, amt={e.amount}')
    
    # Check Flight Ticket entries (now differentiated: FLIGHT TICKET(I) for income, FLIGHT TICKET(E) for expense)
    ft_exp = Expense.query.filter_by(category='FLIGHT TICKET(E)').all()
    ft_income = Income.query.filter_by(category='FLIGHT TICKET(I)').all()
    ft_tzs = TzsIncome.query.filter_by(category='FLIGHT TICKET(I)').all()
    print(f'\\nExpense.FLIGHT TICKET(E) count: {len(ft_exp)}')
    print(f'Income.FLIGHT TICKET(I) count: {len(ft_income)}')
    print(f'TzsIncome.FLIGHT TICKET(I) count: {len(ft_tzs)}')
    
    # Test filtering logic
    print('\\n--- Testing category filtering ---')
    with app.app_context():
        from datetime import date
        from sqlalchemy import func
        
        # Simulate NSSF expense filter
        query = Expense.query.filter(Expense.date >= date(2024, 1, 1), Expense.date <= date.today())
        if 'NSSF' in ['Services', 'Flight Ticket', 'Director Income', 'Other Income']:
            print('NSSF is in income cats')
        else:
            print('NSSF is NOT in income cats')
            
        if 'NSSF' in ['NSSF', 'Salary', 'Rent', 'Internet', 'Fuel', 'Stationary', 'Flight Ticket', 'Payee', 'Insurance', 'Transportation', 'VAT', 'Utilities', 'Loan', 'Apart-Hotel', 'CIP', 'Director Expenses', 'Refund']:
            print('NSSF is in expense cats')
        else:
            print('NSSF is NOT in expense cats')
            
        nssf_query = Expense.query.filter(Expense.category == 'NSSF', Expense.date >= date(2024, 1, 1), Expense.date <= date.today()).all()
        print(f'NSSF expenses found: {len(nssf_query)}')