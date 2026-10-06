from app.reference_data import carregar_apartamentos, carregar_areas

def test_carregar_areas_reflete_o_json():
    areas = carregar_areas()
    assert areas["salao-de-festas"].taxa == 150.0
    assert areas["churrasqueira"].taxa == 80.0
    assert areas["quadra"].taxa == 0
    assert areas["quadra"].nome == "Quadra poliesportiva"

def test_carregar_apartamentos_reflete_o_json():
    apartamentos = carregar_apartamentos()
    assert apartamentos["101"].morador == "Helena Prado"
    assert apartamentos["302"].morador == "Rafael Moreira"