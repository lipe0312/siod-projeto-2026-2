"""Fonte tabular: Áreas Embargadas do IBAMA (CSV)."""

import pandas as pd
import shapely

from pipeline import config
from pipeline.documentos import digito_valido, pseudonimizar, somente_digitos, tipo_documento
from pipeline.download import baixar
from pipeline.validacao import Marcas, ResultadoFonte

COLUNAS_OBRIGATORIAS = [
    "SEQ_TAD", "NUM_TAD", "SER_TAD", "DAT_EMBARGO", "DAT_ULT_ALTERACAO", "COD_UF_TAD", "SIG_UF_TAD",
    "COD_MUNICIPIO_TAD", "NOM_MUNICIPIO_TAD", "NUM_LATITUDE_TAD", "NUM_LONGITUDE_TAD", "CPF_CNPJ_EMBARGADO",
    "QTD_AREA_EMBARGADA", "DES_TIPO_BIOMA", "WKT_GEOM_AREA_EMBARGADA", "DES_INFRACAO",
]

COLUNAS_SAIDA = [
    "id_embargo", "num_tad", "ser_tad", "seq_tad", "data_embargo", "data_ultima_alteracao", "pos_corte_eudr",
    "documento_hash", "tipo_documento", "cod_municipio", "municipio", "uf", "latitude", "longitude", "area_ha",
    "biomas", "geometria_wkt", "descricao_infracao", "alertas",
]

FORMATO_DATA = "%d/%m/%Y %H:%M:%S"
DATA_MINIMA = pd.Timestamp("1980-01-01")


def ler(caminho) -> pd.DataFrame:
    """Lê tudo como texto; a tipagem é feita explicitamente em `transformar`."""
    return pd.read_csv(caminho, sep=";", encoding="utf-8", dtype=str, keep_default_na=False, low_memory=False)


def transformar(bruto: pd.DataFrame, chave: bytes, ref_municipios: pd.DataFrame, hoje: pd.Timestamp,
                resultado: ResultadoFonte) -> tuple[pd.DataFrame, pd.DataFrame]:
    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in bruto.columns]
    resultado.validar("IBAMA_COLUNAS_OBRIGATORIAS", f"Colunas obrigatórias presentes (ausentes: {faltando or 'nenhuma'})",
                      "erro", "interrompe a fonte", len(faltando), len(COLUNAS_OBRIGATORIAS))
    resultado.validar("IBAMA_SEM_REGISTROS", "Arquivo com ao menos um registro", "erro", "interrompe a fonte",
                      int(len(bruto) == 0), 1)
    n = len(bruto)

    df = bruto[COLUNAS_OBRIGATORIAS].apply(lambda c: c.str.strip()).replace("", pd.NA)
    resultado.transformar("Seleção das 16 colunas relevantes; remoção de espaços; texto vazio vira ausente")

    sem_termo = df["NUM_TAD"].isna()
    resultado.validar("IBAMA_NUMERO_TERMO_AUSENTE", "Registro sem número do termo de embargo", "descarte",
                      "registro vai para descartados", sem_termo, n)
    descartados = [df[sem_termo].assign(motivo="IBAMA_NUMERO_TERMO_AUSENTE")]
    df = df[~sem_termo].copy()
    marcas = Marcas(df.index)

    df["id_embargo"] = df["NUM_TAD"] + "-" + df["SER_TAD"].fillna("") + "-" + df["SEQ_TAD"].fillna("")
    resultado.transformar("Identificador id_embargo = número + série + sequencial do termo")
    resultado.validar("IBAMA_ID_DUPLICADO", "id_embargo único", "erro", "interrompe a fonte",
                      df["id_embargo"].duplicated(), len(df))

    # Documento do responsável
    doc = somente_digitos(df["CPF_CNPJ_EMBARGADO"])
    ausente = doc.isna()
    tamanho_invalido = ~ausente & ~doc.str.len().isin([11, 14]).fillna(False)
    dv_invalido = ~ausente & ~tamanho_invalido & ~digito_valido(doc)
    resultado.validar("IBAMA_DOC_AUSENTE", "CPF/CNPJ ausente", "alerta",
                      "registro mantido, sem vínculo por documento", ausente, len(df))
    resultado.validar("IBAMA_DOC_TAMANHO_INVALIDO", "CPF/CNPJ sem 11 ou 14 dígitos", "alerta",
                      "documento anulado", tamanho_invalido, len(df))
    resultado.validar("IBAMA_DOC_DV_INVALIDO", "CPF/CNPJ com dígito verificador inválido", "alerta",
                      "documento anulado", dv_invalido, len(df))
    for codigo, mascara in (("DOC_AUSENTE", ausente), ("DOC_TAMANHO_INVALIDO", tamanho_invalido),
                            ("DOC_DV_INVALIDO", dv_invalido)):
        marcas.marcar(codigo, mascara)
    doc = doc.mask(tamanho_invalido | dv_invalido)
    df["tipo_documento"] = tipo_documento(doc)
    df["documento_hash"] = pseudonimizar(doc, chave)
    resultado.transformar("CPF/CNPJ reduzido a dígitos, validado e substituído por HMAC-SHA256 (documento original removido)")

    # Datas
    data = pd.to_datetime(df["DAT_EMBARGO"], format=FORMATO_DATA, errors="coerce")
    data_invalida = df["DAT_EMBARGO"].notna() & (data.isna() | (data < DATA_MINIMA))
    data_futura = data > hoje
    resultado.validar("IBAMA_DATA_EMBARGO_INVALIDA", "Data do embargo fora do formato esperado ou anterior a 1980",
                      "alerta", "data anulada", data_invalida, len(df))
    resultado.validar("IBAMA_DATA_EMBARGO_FUTURA", "Data do embargo posterior à data de execução", "alerta",
                      "data anulada", data_futura, len(df))
    marcas.marcar("DATA_EMBARGO_INVALIDA", data_invalida)
    marcas.marcar("DATA_EMBARGO_FUTURA", data_futura)
    df["data_embargo"] = data.mask(data_invalida | data_futura)
    df["data_ultima_alteracao"] = pd.to_datetime(df["DAT_ULT_ALTERACAO"], format=FORMATO_DATA, errors="coerce")
    df["pos_corte_eudr"] = (df["data_embargo"] > pd.Timestamp(config.DATA_CORTE_EUDR)).astype("boolean").mask(
        df["data_embargo"].isna())
    resultado.transformar("Datas convertidas de texto (DD/MM/AAAA HH:MM:SS); marcação pos_corte_eudr (após 31/12/2020)")

    # Município e UF
    ref = ref_municipios.set_index("cod_municipio")
    desconhecido = ~df["COD_MUNICIPIO_TAD"].isin(ref.index)
    uf_divergente = ~desconhecido & (df["COD_MUNICIPIO_TAD"].str[:2] != df["COD_UF_TAD"])
    resultado.validar("IBAMA_MUNICIPIO_DESCONHECIDO", "Código de município inexistente na referência do IBGE",
                      "alerta", "mantido com nome e UF da própria base", desconhecido, len(df))
    resultado.validar("IBAMA_MUNICIPIO_UF_DIVERGENTE", "Código do município pertence a outra UF", "alerta",
                      "mantido; UF passa a ser a do município no IBGE", uf_divergente, len(df))
    marcas.marcar("MUNICIPIO_DESCONHECIDO", desconhecido)
    marcas.marcar("MUNICIPIO_UF_DIVERGENTE", uf_divergente)
    df["cod_municipio"] = df["COD_MUNICIPIO_TAD"]
    df["municipio"] = df["cod_municipio"].map(ref["municipio"]).fillna(df["NOM_MUNICIPIO_TAD"])
    df["uf"] = df["cod_municipio"].map(ref["uf"]).fillna(df["SIG_UF_TAD"])
    resultado.transformar("Nome do município e UF padronizados pela referência do IBGE a partir do código")

    # Coordenadas
    lat = pd.to_numeric(df["NUM_LATITUDE_TAD"], errors="coerce")
    lon = pd.to_numeric(df["NUM_LONGITUDE_TAD"], errors="coerce")
    lim = config.LIMITES_BRASIL
    incompleta = lat.isna() != lon.isna()
    zero = (lat == 0) & (lon == 0)
    fora = lat.notna() & lon.notna() & ~zero & ~(lat.between(lim["lat_min"], lim["lat_max"])
                                                 & lon.between(lim["lon_min"], lim["lon_max"]))
    resultado.validar("IBAMA_COORD_INCOMPLETA", "Só latitude ou só longitude preenchida", "alerta",
                      "coordenada anulada", incompleta, len(df))
    resultado.validar("IBAMA_COORD_ZERO", "Coordenada (0, 0)", "alerta", "coordenada anulada", zero, len(df))
    resultado.validar("IBAMA_COORD_FORA_BRASIL", "Coordenada fora do retângulo do território brasileiro",
                      "alerta", "coordenada anulada", fora, len(df))
    for codigo, mascara in (("COORD_INCOMPLETA", incompleta), ("COORD_ZERO", zero), ("COORD_FORA_BRASIL", fora)):
        marcas.marcar(codigo, mascara)
    anular = incompleta | zero | fora
    df["latitude"], df["longitude"] = lat.mask(anular), lon.mask(anular)

    # Área
    area = pd.to_numeric(df["QTD_AREA_EMBARGADA"].str.replace(",", ".", regex=False), errors="coerce")
    area_invalida = df["QTD_AREA_EMBARGADA"].notna() & area.isna()
    area_nao_positiva = area <= 0
    resultado.validar("IBAMA_AREA_INVALIDA", "Área embargada não numérica", "alerta", "área anulada",
                      area_invalida, len(df))
    resultado.validar("IBAMA_AREA_NAO_POSITIVA", "Área embargada igual a zero ou negativa", "alerta",
                      "área anulada", area_nao_positiva, len(df))
    marcas.marcar("AREA_INVALIDA", area_invalida)
    marcas.marcar("AREA_NAO_POSITIVA", area_nao_positiva)
    df["area_ha"] = area.mask(area_nao_positiva)
    resultado.transformar("Área convertida de texto com vírgula decimal para número (hectares)")

    # Bioma
    def normalizar_biomas(valor):
        if pd.isna(valor):
            return pd.NA, False
        itens = [i.strip() for i in valor.split(",") if i.strip()]
        desconhecido = any(i not in config.BIOMAS for i in itens)
        conhecidos = sorted({config.BIOMAS[i] for i in itens if i in config.BIOMAS})
        return (", ".join(conhecidos) if conhecidos else pd.NA), desconhecido

    normalizado = df["DES_TIPO_BIOMA"].map(normalizar_biomas)
    df["biomas"] = normalizado.str[0].astype("string")
    bioma_desconhecido = normalizado.str[1].astype(bool)
    alterado = df["DES_TIPO_BIOMA"].notna() & (df["biomas"] != df["DES_TIPO_BIOMA"]).fillna(True)
    resultado.validar("IBAMA_BIOMA_NORMALIZADO", "Bioma com repetição, ordem variável ou sem acento", "correcao",
                      "itens únicos, ordenados e acentuados", alterado, int(df["DES_TIPO_BIOMA"].notna().sum()))
    resultado.validar("IBAMA_BIOMA_DESCONHECIDO", "Bioma fora do domínio conhecido", "alerta",
                      "item desconhecido removido", bioma_desconhecido, int(df["DES_TIPO_BIOMA"].notna().sum()))
    marcas.marcar("BIOMA_DESCONHECIDO", bioma_desconhecido)

    # Geometria
    wkt = df["WKT_GEOM_AREA_EMBARGADA"]
    tem_wkt = wkt.notna()
    geom = pd.Series(None, index=df.index, dtype=object)
    geom[tem_wkt] = shapely.from_wkt(wkt[tem_wkt].to_numpy(), on_invalid="ignore")
    ilegivel = tem_wkt & geom.isna()
    lida = geom.notna()
    tipo_invalido = pd.Series(False, index=df.index)
    tipo_invalido[lida] = ~pd.Series(shapely.get_type_id(geom[lida].to_numpy()), index=geom[lida].index).isin([3, 6])
    limites = pd.DataFrame(index=df.index, columns=["xmin", "ymin", "xmax", "ymax"], dtype=float)
    limites.loc[lida] = shapely.bounds(geom[lida].to_numpy())
    geom_fora = lida & ~tipo_invalido & ~((limites["ymin"] >= lim["lat_min"]) & (limites["ymax"] <= lim["lat_max"])
                                           & (limites["xmin"] >= lim["lon_min"]) & (limites["xmax"] <= lim["lon_max"]))
    geom_invalida = pd.Series(False, index=df.index)
    geom_invalida[lida] = ~shapely.is_valid(geom[lida].to_numpy())
    geom_invalida &= ~tipo_invalido & ~geom_fora
    resultado.validar("IBAMA_GEOM_ILEGIVEL", "WKT que não pode ser lido", "alerta", "geometria anulada",
                      ilegivel, int(tem_wkt.sum()))
    resultado.validar("IBAMA_GEOM_TIPO_INVALIDO", "Geometria que não é polígono ou multipolígono", "alerta",
                      "geometria anulada", tipo_invalido, int(tem_wkt.sum()))
    resultado.validar("IBAMA_GEOM_FORA_BRASIL", "Geometria fora do retângulo do território brasileiro", "alerta",
                      "geometria anulada", geom_fora, int(tem_wkt.sum()))
    resultado.validar("IBAMA_GEOM_INVALIDA", "Polígono topologicamente inválido (ex.: autointerseção)", "alerta",
                      "geometria mantida sem correção", geom_invalida, int(tem_wkt.sum()))
    for codigo, mascara in (("GEOM_ILEGIVEL", ilegivel), ("GEOM_TIPO_INVALIDO", tipo_invalido),
                            ("GEOM_FORA_BRASIL", geom_fora), ("GEOM_INVALIDA", geom_invalida)):
        marcas.marcar(codigo, mascara)
    df["geometria_wkt"] = wkt.mask(ilegivel | tipo_invalido | geom_fora)
    resultado.transformar("Geometria WKT lida e verificada (tipo, limites e validade topológica)")

    # Registro sem vínculo nem localização não serve ao sistema
    inutilizavel = df["documento_hash"].isna() & df["geometria_wkt"].isna() & df["latitude"].isna()
    resultado.validar("IBAMA_SEM_VINCULO_NEM_LOCALIZACAO",
                      "Sem documento válido, sem geometria e sem coordenada válida", "descarte",
                      "registro vai para descartados", inutilizavel, len(df))

    df["num_tad"], df["ser_tad"], df["seq_tad"] = df["NUM_TAD"], df["SER_TAD"], df["SEQ_TAD"]
    df["descricao_infracao"] = df["DES_INFRACAO"]
    df["alertas"] = marcas.coluna()
    saida = df.loc[~inutilizavel, COLUNAS_SAIDA].reset_index(drop=True)
    descartados.append(df.loc[inutilizavel].assign(motivo="IBAMA_SEM_VINCULO_NEM_LOCALIZACAO"))
    descartes = pd.concat(descartados)
    colunas_descarte = [c for c in COLUNAS_SAIDA if c in descartes.columns] + ["motivo"]
    descartes = descartes.reindex(columns=colunas_descarte).reset_index(drop=True)
    resultado.transformar("Remoção do documento original, do nome do responsável e de colunas não usadas")
    return saida, descartes


def executar(chave: bytes, ref_municipios: pd.DataFrame, hoje: pd.Timestamp, atualizar: bool = False) -> ResultadoFonte:
    resultado = ResultadoFonte("ibama_embargos", "tabular (CSV)")
    destino = config.DADOS_BRUTOS / "areas_embargadas.csv"
    resultado.entrada = baixar(config.URL_IBAMA_EMBARGOS, destino, atualizar)
    bruto = ler(destino)
    resultado.entrada.update(registros_recebidos=len(bruto), colunas_recebidas=bruto.shape[1])
    resultado.transformar("Leitura do CSV com separador ';', UTF-8 e todas as colunas como texto")

    saida, descartados = transformar(bruto, chave, ref_municipios, hoje, resultado)
    config.DADOS_PROCESSADOS.mkdir(parents=True, exist_ok=True)
    arq_saida = config.DADOS_PROCESSADOS / "ibama_embargos.parquet"
    arq_desc = config.DADOS_PROCESSADOS / "ibama_embargos_descartados.parquet"
    saida.to_parquet(arq_saida, index=False)
    descartados.to_parquet(arq_desc, index=False)
    resultado.saida = {
        "arquivo": str(arq_saida.relative_to(config.RAIZ)),
        "registros_produzidos": len(saida),
        "registros_com_alerta": int((saida["alertas"] != "").sum()),
        "colunas": list(saida.columns),
        "arquivo_descartados": str(arq_desc.relative_to(config.RAIZ)),
        "registros_descartados": len(descartados),
    }
    resultado.status = "ok"
    return resultado
