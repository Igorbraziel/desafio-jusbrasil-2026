from verificador.contrato import Citacao, SaidaDocumento, validar


def _saida_valida():
    return SaidaDocumento(
        documento_id="doc_0042",
        citacoes=[
            Citacao(
                id="c1",
                inicio=10,
                fim=27,
                trecho="REsp 1.234.567/SP",
                tipo="jurisprudencia",
                classificacao="real",
                id_canonico=2106313729,
                confianca=0.91,
            )
        ],
    ).para_dicionario()


def test_saida_valida_nao_tem_problemas():
    assert validar(_saida_valida()) == []


def test_real_carrega_id_canonico():
    resolucao = _saida_valida()["citacoes"][0]["resolucao"]
    assert resolucao == {"fonte": "jusbrasil", "id_canonico": "2106313729"}


def test_classe_nao_real_tem_resolucao_nula():
    saida = SaidaDocumento(
        documento_id="doc_0042",
        citacoes=[Citacao("c1", 0, 5, "aaaaa", "jurisprudencia", "incompleta", id_canonico=999)],
    ).para_dicionario()
    assert saida["citacoes"][0]["resolucao"] is None
    assert validar(saida) == []


def test_real_sem_id_canonico_e_rejeitada():
    saida = _saida_valida()
    saida["citacoes"][0]["resolucao"] = None
    assert any("id_canonico" in p for p in validar(saida))


def test_span_invertido_e_rejeitado():
    saida = _saida_valida()
    saida["citacoes"][0]["fim"] = saida["citacoes"][0]["inicio"]
    assert any("span inválido" in p for p in validar(saida))


def test_trecho_conferido_contra_o_texto():
    saida = _saida_valida()
    texto = " " * 10 + "REsp 1.234.567/SP" + " fim"
    assert validar(saida, texto) == []
    assert validar(saida, texto.replace("1.234.567", "9.999.999"))


def test_confianca_fora_do_intervalo():
    saida = _saida_valida()
    saida["citacoes"][0]["confianca"] = 1.4
    assert any("confianca" in p for p in validar(saida))
