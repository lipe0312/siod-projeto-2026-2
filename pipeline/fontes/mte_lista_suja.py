"""Fonte documento: Cadastro de Empregadores do Ministério do Trabalho ("Lista Suja"), publicado em PDF."""

import hashlib
import re

import pandas as pd
import pdfplumber

from pipeline import config
from pipeline.armazenamento import lago
from pipeline.documentos import digito_valido, pseudonimizar, somente_digitos, tipo_documento
from pipeline.download import baixar
from pipeline.validacao import Marcas, ResultadoFonte

CABECALHO_ESPERADO = [
    "ID", "Ano da ação fiscal", "UF", "Empregador", "CNPJ/CPF", "Estabelecimento", "Trabalhadores envolvidos",
    "CNAE", "Decisão administrativa de procedência", "Inclusão no Cadastro de Empregadores",
]
COLUNAS_INTERNAS = [
    "id", "ano", "uf", "empregador", "documento", "estabelecimento", "trabalhadores", "cnae", "decisao", "inclusao",
]
COLUNAS_SAIDA = [
    "chave_registro", "id_registro", "documento_hash", "tipo_documento", "uf", "estabelecimento", "cnae", "cnae_agropecuaria",
    "trabalhadores_envolvidos", "ano_acao_fiscal", "data_decisao", "data_inclusao", "data_inclusao_ultima",
    "data_atualizacao_cadastro", "alertas",
]
PADRAO_DATA = re.compile(r"\d{2}/\d{2}/\d{4}")
TABELA = "ref.lista_suja"


def _limpar(celula) -> str:
    return re.sub(r"\s+", " ", (celula or "").replace("\n", " ")).strip()


def chave_registro(df: pd.DataFrame) -> pd.Series:
    """Chave estável do registro: id_registro é a linha do PDF e muda a cada versão. Vem do documento (já em HMAC), do
    estabelecimento e do ano da ação fiscal (vazio quando nulo), mais um sequencial para os registros que repetem essa
    tripla com outro número de trabalhadores (ordem do PDF). Hash de 32 dígitos, sem dado pessoal em claro."""
    base = (df["documento_hash"].fillna("") + "|" + df["estabelecimento"].fillna("") + "|"
            + df["ano_acao_fiscal"].astype("string").fillna(""))
    sequencial = df.assign(_base=base).sort_values("id_registro").groupby("_base").cumcount().reindex(df.index)
    return (base + "|" + sequencial.astype(str)).map(lambda t: hashlib.sha256(t.encode()).hexdigest()[:32])


def extrair(caminho) -> tuple[list[str], list[list[list[str]]]]:
    """Texto e tabela de cada página do PDF."""
    textos, tabelas = [], []
    with pdfplumber.open(caminho) as pdf:
        for pagina in pdf.pages:
            textos.append(pagina.extract_text() or "")
            tabelas.append(pagina.extract_table() or [])
    return textos, tabelas


def segmentar(tabelas: list, resultado: ResultadoFonte) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Separa cada linha extraída em cabeçalho, título de página, registro ou linha não reconhecida."""
    registros, nao_reconhecidas, cabecalhos_inesperados = [], [], []
    contagem = {"cabecalho": 0, "titulo": 0}
    total = 0
    for numero_pagina, tabela in enumerate(tabelas, start=1):
        for linha in tabela:
            total += 1
            celulas = [_limpar(c) for c in linha]
            primeira = celulas[0] if celulas else ""
            if primeira == "ID":
                contagem["cabecalho"] += 1
                if celulas != CABECALHO_ESPERADO:
                    cabecalhos_inesperados.append(numero_pagina)
            elif primeira.isdigit() and len(celulas) == len(CABECALHO_ESPERADO):
                registros.append(dict(zip(COLUNAS_INTERNAS, celulas), pagina=numero_pagina))
            elif primeira and not any(celulas[1:]):
                contagem["titulo"] += 1
            else:
                nao_reconhecidas.append({"pagina": numero_pagina, "celulas_preenchidas": sum(bool(c) for c in celulas)})
    resultado.validar("LS_CABECALHO_INESPERADO", "Cabeçalho da tabela diferente das 10 colunas esperadas"
                      + (f" (páginas {cabecalhos_inesperados[:5]})" if cabecalhos_inesperados else ""),
                      "erro", "interrompe a fonte", len(cabecalhos_inesperados), max(contagem["cabecalho"], 1))
    resultado.transformar(f"Segmentação das {total} linhas extraídas: {contagem['cabecalho']} cabeçalhos repetidos e "
                          f"{contagem['titulo']} títulos de página removidos; {len(registros)} registros")
    resultado.validar("LS_LINHA_NAO_RECONHECIDA", "Linha que não é cabeçalho, título nem registro", "descarte",
                      "linha vai para descartados", len(nao_reconhecidas), total)
    resultado.validar("LS_SEM_REGISTROS", "Nenhum registro extraído do documento", "erro", "interrompe a fonte",
                      int(not registros), 1)
    return pd.DataFrame(registros), pd.DataFrame(nao_reconhecidas, columns=["pagina", "celulas_preenchidas"])


def transformar(textos: list[str], tabelas: list, chave: bytes, hoje: pd.Timestamp,
                resultado: ResultadoFonte) -> tuple[pd.DataFrame, pd.DataFrame]:
    vazias = [t.strip() == "" for t in textos]
    resultado.validar("LS_DOCUMENTO_VAZIO", "Nenhum texto extraído do PDF", "erro", "interrompe a fonte",
                      int(not textos or all(vazias)), 1)
    resultado.validar("LS_PAGINA_SEM_TEXTO", "Página sem texto extraível", "alerta", "página ignorada",
                      sum(vazias), len(textos))

    achado = re.search(r"Cadastro atualizado em (\d{2}/\d{2}/\d{4})", "\n".join(textos[:1]))
    resultado.validar("LS_DATA_ATUALIZACAO_AUSENTE", "Data de atualização do cadastro não encontrada no documento",
                      "alerta", "campo data_atualizacao_cadastro fica vazio", int(not achado), 1)
    atualizacao = pd.to_datetime(achado.group(1), format="%d/%m/%Y") if achado else pd.NaT

    df, descartados = segmentar(tabelas, resultado)
    n = len(df)
    marcas = Marcas(df.index)

    df["id_registro"] = df["id"].astype(int)
    resultado.validar("LS_ID_DUPLICADO", "ID do registro único", "erro", "interrompe a fonte",
                      df["id_registro"].duplicated(), n)

    doc = somente_digitos(df["documento"])
    formato_invalido = ~doc.str.len().isin([11, 14]).fillna(False)
    dv_invalido = ~formato_invalido & ~digito_valido(doc)
    resultado.validar("LS_DOC_FORMATO_INVALIDO", "CPF/CNPJ ausente ou sem 11 ou 14 dígitos", "alerta",
                      "documento anulado", formato_invalido, n)
    resultado.validar("LS_DOC_DV_INVALIDO", "CPF/CNPJ com dígito verificador inválido", "alerta",
                      "documento anulado", dv_invalido, n)
    marcas.marcar("DOC_FORMATO_INVALIDO", formato_invalido)
    marcas.marcar("DOC_DV_INVALIDO", dv_invalido)
    doc = doc.mask(formato_invalido | dv_invalido)
    repetido = doc.notna() & doc.duplicated(keep=False)
    resultado.validar("LS_DOC_REPETIDO", "Mesmo empregador em mais de um registro", "alerta",
                      "mantido (estabelecimentos diferentes)", repetido, n)
    marcas.marcar("DOC_REPETIDO", repetido)
    df["tipo_documento"] = tipo_documento(doc)
    df["documento_hash"] = pseudonimizar(doc, chave)
    resultado.transformar("CPF/CNPJ reduzido a dígitos, validado e substituído por HMAC-SHA256; nome do empregador removido")

    uf_invalida = ~df["uf"].isin(config.UFS)
    resultado.validar("LS_UF_INVALIDA", "UF ausente ou fora das 27 siglas", "alerta", "UF anulada", uf_invalida, n)
    marcas.marcar("UF_INVALIDA", uf_invalida)
    df["uf"] = df["uf"].mask(uf_invalida)

    ano = pd.to_numeric(df["ano"], errors="coerce")
    ano_invalido = ano.isna() | (ano < 1995) | (ano > hoje.year)
    resultado.validar("LS_ANO_ACAO_INVALIDO", "Ano da ação fiscal ausente ou fora de 1995 até o ano atual", "alerta",
                      "ano anulado", ano_invalido, n)
    marcas.marcar("ANO_ACAO_INVALIDO", ano_invalido)
    df["ano_acao_fiscal"] = ano.mask(ano_invalido).astype("Int64")

    trabalhadores = pd.to_numeric(df["trabalhadores"], errors="coerce")
    trab_invalido = trabalhadores.isna() | (trabalhadores < 1) | (trabalhadores % 1 != 0)
    resultado.validar("LS_TRABALHADORES_INVALIDO", "Número de trabalhadores ausente ou não inteiro positivo",
                      "alerta", "valor anulado", trab_invalido, n)
    marcas.marcar("TRABALHADORES_INVALIDO", trab_invalido)
    df["trabalhadores_envolvidos"] = trabalhadores.mask(trab_invalido).astype("Int64")

    cnae_invalido = ~df["cnae"].str.fullmatch(r"\d{4}-\d/\d{2}")
    resultado.validar("LS_CNAE_FORMATO_INVALIDO", "CNAE ausente ou fora do formato 9999-9/99", "alerta",
                      "CNAE anulado", cnae_invalido, n)
    marcas.marcar("CNAE_FORMATO_INVALIDO", cnae_invalido)
    df["cnae"] = df["cnae"].mask(cnae_invalido)
    df["cnae_agropecuaria"] = df["cnae"].str[:2].isin(["01", "02", "03"]).astype("boolean").mask(cnae_invalido)
    resultado.transformar("CNAE validado; marcação cnae_agropecuaria para as divisões 01 a 03 (seção A)")

    decisao = pd.to_datetime(df["decisao"], format="%d/%m/%Y", errors="coerce")
    datas_inclusao = df["inclusao"].map(PADRAO_DATA.findall)
    inclusao = pd.to_datetime(datas_inclusao.str[0], format="%d/%m/%Y", errors="coerce")
    inclusao_ultima = pd.to_datetime(datas_inclusao.str[-1], format="%d/%m/%Y", errors="coerce")
    multiplos = datas_inclusao.str.len() > 1
    decisao_invalida = decisao.isna() | (decisao > hoje)
    inclusao_invalida = inclusao.isna() | (inclusao_ultima > hoje)
    antes_da_decisao = ~decisao_invalida & ~inclusao_invalida & (inclusao < decisao)
    resultado.validar("LS_DATA_DECISAO_INVALIDA", "Data da decisão ausente, fora do formato ou futura", "alerta",
                      "data anulada", decisao_invalida, n)
    resultado.validar("LS_DATA_INCLUSAO_INVALIDA", "Data de inclusão ausente, fora do formato ou futura", "alerta",
                      "datas anuladas", inclusao_invalida, n)
    resultado.validar("LS_INCLUSAO_MULTIPLOS_PERIODOS", "Célula de inclusão com mais de uma data (vários períodos)",
                      "correcao", "primeira e última data extraídas em colunas separadas", multiplos, n)
    resultado.validar("LS_INCLUSAO_ANTES_DA_DECISAO", "Inclusão no cadastro anterior à decisão administrativa",
                      "alerta", "mantido", antes_da_decisao, n)
    marcas.marcar("DATA_DECISAO_INVALIDA", decisao_invalida)
    marcas.marcar("DATA_INCLUSAO_INVALIDA", inclusao_invalida)
    marcas.marcar("INCLUSAO_ANTES_DA_DECISAO", antes_da_decisao)
    df["data_decisao"] = decisao.mask(decisao_invalida)
    df["data_inclusao"] = inclusao.mask(inclusao_invalida)
    df["data_inclusao_ultima"] = inclusao_ultima.mask(inclusao_invalida)
    df["data_atualizacao_cadastro"] = atualizacao
    resultado.transformar("Datas de decisão e inclusão convertidas de texto; data de atualização lida do cabeçalho do documento")
    df["chave_registro"] = chave_registro(df)
    resultado.transformar("Chave chave_registro = hash de documento + estabelecimento + ano da ação + sequencial "
                          "(id_registro é a linha do PDF e não é estável)")

    df["alertas"] = marcas.coluna()
    return df[COLUNAS_SAIDA].reset_index(drop=True), descartados


def executar(chave: bytes, hoje: pd.Timestamp, atualizar: bool = False) -> ResultadoFonte:
    resultado = ResultadoFonte("mte_lista_suja", "documento (PDF)")
    destino = config.DADOS_BRUTOS / "lista_suja.pdf"
    resultado.entrada = baixar(config.URL_LISTA_SUJA, destino, atualizar)
    textos, tabelas = extrair(destino)
    resultado.entrada.update(paginas=len(textos), linhas_de_tabela=sum(len(t) for t in tabelas))
    resultado.transformar("Extração do texto e da tabela de cada página do PDF (pdfplumber)")

    saida, descartados = transformar(textos, tabelas, chave, hoje, resultado)
    resultado.entrada["registros_recebidos"] = len(saida) + len(descartados)
    lago.gravar(TABELA, saida, resultado)
    resultado.saida.update({
        "arquivo": lago.relativo(lago.pasta(TABELA)),
        "registros_produzidos": len(saida),
        "registros_com_alerta": int((saida["alertas"] != "").sum()),
        "colunas": list(saida.columns),
        "registros_descartados": len(descartados),
    })
    resultado.status = "ok"
    return resultado
