from app.regulamento import carregar_capitulos

def test_divide_em_14_capitulos():
    capitulos = carregar_capitulos()
    assert len(capitulos) == 14
    assert capitulos[0].titulo == "Capítulo I: Disposições gerais"
    assert capitulos[-1].titulo == "Capítulo XIV: Disposições finais"

def test_conteudo_de_um_capitulo_nao_vaza_para_o_outro():
    capitulos = carregar_capitulos()
    piscina = next(c for c in capitulos if c.titulo == "Capítulo IV: Piscina")
    assert "piscina" in piscina.conteudo.lower()
    assert "Capítulo V" not in piscina.conteudo