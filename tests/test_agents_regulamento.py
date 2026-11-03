from app.agents.regulamento import build_especialista_regulamento, consultar_regulamento


def test_consultar_capitulo_existente_devolve_so_aquele_conteudo():
    resultado = consultar_regulamento(titulo_capitulo="Capítulo IV: Piscina")
    assert resultado["titulo"] == "Capítulo IV: Piscina"
    assert "piscina" in resultado["conteudo"].lower()
    assert "Capítulo V" not in resultado["conteudo"]


def test_consultar_capitulo_inexistente_devolve_erro_e_lista_capitulos():
    resultado = consultar_regulamento(titulo_capitulo="Capítulo XCIX: Não existe")
    assert "erro" in resultado
    assert "Capítulo I: Disposições gerais" in resultado["capitulos_disponiveis"]


def test_build_especialista_regulamento_nao_tem_o_regulamento_na_instrucao_toda():
    agente = build_especialista_regulamento()
    assert len(agente.tools) == 1
    assert agente.tools[0].name == "consultar_regulamento"
    # a instrução lista só os TÍTULOS dos capítulos, nunca o conteúdo deles.
    assert "piscina das" not in agente.instruction.lower()
    assert "Capítulo IV: Piscina" in agente.instruction
