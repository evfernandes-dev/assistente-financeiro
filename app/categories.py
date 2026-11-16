DEFAULT_CATEGORIES: tuple[tuple[str, str], ...] = (
    ("Alimentação", "expense"),
    ("Transporte", "expense"),
    ("Moradia", "expense"),
    ("Saúde", "expense"),
    ("Educação", "expense"),
    ("Lazer", "expense"),
    ("Assinaturas", "expense"),
    ("Outros", "expense"),
    ("Salário", "income"),
    ("Outras receitas", "income"),
)

CATEGORY_NAMES: tuple[str, ...] = tuple(name for name, _ in DEFAULT_CATEGORIES)
