from app.reference_data import carregar_areas


def test_carregar_areas_reflete_o_json():
    areas = carregar_areas()
    assert areas["salao-de-festas"].taxa == 150.0
    assert areas["churrasqueira"].taxa == 80.0
    assert areas["quadra"].taxa == 0
    assert areas["quadra"].nome == "Quadra poliesportiva"
