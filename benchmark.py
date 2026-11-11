"""Experimentos reproduzíveis de latência CPU + GPU, com amostras auditáveis.

Cada duração inclui construção, envio e conclusão do quadro (ctx.finish).
Não mede tempo exclusivo da GPU, apresentação na tela ou WCET. Estatística e
exportação podem ser usadas sem bibliotecas gráficas ou contexto OpenGL.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from contextlib import ExitStack
from copy import deepcopy
import csv
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import statistics
import sys
import time
import uuid

from configuracoes import CONFIGURACOES_EXPERIMENTAIS, obter_configuracoes, validar_configuracao

ESTRATEGIAS = ("Monolítica", "Multicamada")
CENARIOS = ("normal", "trafego", "incendio")
ORCAMENTO_60FPS_MS = 1000.0 / 60.0
PASSO_SIMULACAO = 1.0 / 60.0


def _inteiro(valor, nome, minimo=1):
    if isinstance(valor, bool) or not isinstance(valor, int) or valor < minimo:
        raise ValueError(f"{nome} deve ser inteiro >= {minimo}.")
    return valor


def validar_amostras(amostras):
    """Rejeita medições vazias, não finitas ou não positivas; nunca as mascara."""
    valores = []
    for amostra in amostras:
        if isinstance(amostra, (str, bytes, bool)):
            raise ValueError("Tempos devem ser números finitos e positivos em milissegundos.")
        try:
            valor = float(amostra)
        except (ValueError, TypeError, OverflowError) as erro:
            raise ValueError("Amostra de tempo inválida.") from erro
        if not math.isfinite(valor) or valor <= 0:
            raise ValueError("Tempos devem ser finitos e estritamente positivos.")
        valores.append(valor)
    if not valores:
        raise ValueError("É necessária pelo menos uma amostra de tempo.")
    return valores


def _percentil_ordenado(valores, percentil):
    """Interpolação linear inclusiva, equivalente ao padrão do NumPy."""
    posicao = (len(valores) - 1) * percentil / 100.0
    inferior, superior = int(math.floor(posicao)), int(math.ceil(posicao))
    fracao = posicao - inferior
    return valores[inferior] * (1 - fracao) + valores[superior] * fracao


def calcular_estatisticas(amostras, orcamento_ms=ORCAMENTO_60FPS_MS):
    valores = sorted(validar_amostras(amostras))
    if isinstance(orcamento_ms, bool) or not math.isfinite(orcamento_ms) or orcamento_ms <= 0:
        raise ValueError("O orçamento deve ser finito e positivo.")
    media = statistics.fmean(valores)
    excedidos = sum(valor > orcamento_ms for valor in valores)
    return {
        "frames_medidos": len(valores), "fps_medio": 1000.0 / media,
        "tempo_medio_ms": media, "tempo_std_ms": statistics.pstdev(valores),
        "tempo_mediana_ms": statistics.median(valores),
        "tempo_p95_ms": _percentil_ordenado(valores, 95),
        "tempo_p99_ms": _percentil_ordenado(valores, 99),
        "tempo_min_ms": valores[0], "tempo_max_ms": valores[-1],
        "orcamento_ms": float(orcamento_ms), "frames_fora_orcamento": excedidos,
        "frames_fora_orcamento_pct": 100.0 * excedidos / len(valores),
    }


def _configuracoes_selecionadas(configs):
    if configs is None or isinstance(configs, str):
        return obter_configuracoes(configs)
    lista = list(configs)
    if not lista:
        raise ValueError("Escolha pelo menos uma configuração.")
    if all(isinstance(config, str) for config in lista):
        return obter_configuracoes(lista)
    if not all(isinstance(config, dict) for config in lista):
        raise ValueError("Use uma lista de IDs ou de dicionários de configuração.")
    resultado = [validar_configuracao(config) for config in lista]
    if len({config["id"] for config in resultado}) != len(resultado):
        raise ValueError("Os identificadores das configurações devem ser únicos.")
    return resultado


def _sequencia_dados(quantidade, seed, cenario="incendio"):
    from simulador import SimuladorVoo

    if cenario not in CENARIOS:
        raise ValueError(f"Cenário inválido: {cenario}.")
    simulador = SimuladorVoo(seed=seed, cenario=cenario)
    dados = []
    for _ in range(quantidade):
        simulador.atualizar(dt=PASSO_SIMULACAO)
        # Alertas e alvos contêm listas mutáveis: preservar snapshots independentes.
        dados.append(deepcopy(simulador.obter_dados()))
    return dados


def _segundos_cpu(processo):
    tempos = processo.cpu_times()
    return tempos.user + tempos.system


def _liberar_recursos(*objetos):
    """Tenta liberar todos os recursos mesmo se uma liberação falhar."""
    with ExitStack() as liberacoes:
        for objeto in reversed(objetos):
            if objeto is not None:
                liberacoes.callback(objeto.release)


def executar_teste_configuracao(
    ctx, window, config, estrategia, frames_warmup=60, frames_medicao=300,
    proporcao_transparencia=0.5, *, repeticao=1, seed=42,
    cenario="incendio", quantidade_gaussianas=6000,
    sequencia_dados=None, caminho_captura=None,
):
    """Mede uma repetição em RGBA8 offscreen, sem swaps durante a coleta.

    A dimensão independe de DPI/tamanho de janela. Dados, recursos e captura PNG
    ficam fora do intervalo de cada quadro. Libera objetos GL mesmo sob falha.
    """
    import glfw
    import psutil
    from pipeline import PipelineRenderizacao

    config = validar_configuracao(config)
    _inteiro(frames_warmup, "frames_warmup", 0)
    _inteiro(frames_medicao, "frames_medicao")
    _inteiro(repeticao, "repeticao")
    _inteiro(quantidade_gaussianas, "quantidade_gaussianas")
    if cenario not in CENARIOS:
        raise ValueError(f"Cenário inválido: {cenario}.")
    if estrategia not in ESTRATEGIAS:
        raise ValueError(f"Estratégia inválida: {estrategia}.")
    if not math.isfinite(proporcao_transparencia) or not 0 <= proporcao_transparencia <= 1:
        raise ValueError("A proporção de transparência deve estar entre 0 e 1.")
    dados = sequencia_dados
    if dados is None:
        dados = _sequencia_dados(frames_warmup + frames_medicao, seed, cenario)
    if len(dados) != frames_warmup + frames_medicao:
        raise ValueError("A sequência deve ter warmup + frames_medicao quadros.")
    pipeline = textura = destino = None
    processo = psutil.Process(os.getpid())
    recursos, amostras = [], []
    largura, altura = config["largura"], config["altura"]
    try:
        pipeline = PipelineRenderizacao(ctx, largura, altura, config["camadas"])
        pipeline.interface.seed_cena = seed
        pipeline.interface.quantidade_gaussianas = quantidade_gaussianas
        textura = ctx.texture((largura, altura), components=4, dtype="f1")
        destino = ctx.framebuffer(color_attachments=[textura])
        stress = pipeline.interface.gerador.atualizar_elementos_estresse(
            config["elementos"], config["camadas"], proporcao_transparencia, seed=seed,
        )
        codigo = "MONOLITICA" if estrategia == "Monolítica" else "MULTICAMADA"
        inicio_parede = inicio_cpu = ultimo_tempo = ultimo_cpu = None
        ctx.finish()
        for indice, quadro in enumerate(dados):
            glfw.poll_events()
            if window is not None and glfw.window_should_close(window):
                raise RuntimeError("Benchmark interrompido antes de concluir todas as amostras.")
            if indice == frames_warmup:
                inicio_cpu = ultimo_cpu = _segundos_cpu(processo)
                inicio_parede = ultimo_tempo = time.perf_counter()
            inicio = time.perf_counter_ns()
            pipeline.renderizar(quadro, codigo, num_camadas=config["camadas"], stress_dict=stress, destino=destino)
            ctx.finish()
            fim = time.perf_counter_ns()
            if indice < frames_warmup:
                continue
            amostras.append((fim - inicio) / 1_000_000.0)
            agora = time.perf_counter()
            frame = indice - frames_warmup + 1
            if frame == 1 or agora - ultimo_tempo >= 0.1 or frame == frames_medicao:
                cpu_atual = _segundos_cpu(processo)
                intervalo = agora - ultimo_tempo
                # Intervalos curtos ficam sem percentual; CPU global usa toda a coleta.
                cpu_intervalo = 100 * (cpu_atual - ultimo_cpu) / intervalo if intervalo >= 0.1 else None
                recursos.append({"frame": frame, "ram_mb": processo.memory_info().rss / (1024 ** 2),
                                 "cpu_pct_intervalo": cpu_intervalo, "intervalo_s": intervalo})
                if intervalo >= 0.1:
                    ultimo_tempo, ultimo_cpu = agora, cpu_atual
        duracao = time.perf_counter() - inicio_parede
        cpu_pct = 100 * (_segundos_cpu(processo) - inicio_cpu) / duracao
        resultado = {
            "config_id": config["id"], "elementos": config["elementos"], "camadas": config["camadas"],
            "resolucao": f"{largura}x{altura}", "estrategia": estrategia, "repeticao": repeticao, "seed": seed,
            "frames_warmup": frames_warmup, "transparencia": proporcao_transparencia,
            "cenario": cenario, "quantidade_gaussianas": quantidade_gaussianas,
            **calcular_estatisticas(amostras), "cpu_pct": cpu_pct, "duracao_coleta_s": duracao,
            "ram_mb": statistics.fmean(item["ram_mb"] for item in recursos),
            "ram_max_mb": max(item["ram_mb"] for item in recursos),
            "amostras_tempos": amostras, "amostras_recursos": recursos,
        }
        if caminho_captura is not None:
            from PIL import Image
            caminho = Path(caminho_captura)
            caminho.parent.mkdir(parents=True, exist_ok=True)
            imagem = Image.frombytes("RGBA", (largura, altura), destino.read(components=4, alignment=1))
            imagem.transpose(Image.Transpose.FLIP_TOP_BOTTOM).save(caminho)
        return resultado
    finally:
        # O contexto permanece atual durante todas as liberações.
        _liberar_recursos(destino, textura, pipeline)


def _normalizar_resultado(resultado):
    copia = dict(resultado)
    copia["amostras_tempos"] = validar_amostras(resultado["amostras_tempos"])
    copia.update(calcular_estatisticas(copia["amostras_tempos"]))
    copia.setdefault("repeticao", 1)
    return copia


def agregar_resultados(resultados):
    """Agrupa todas as repetições, sem sobrescrever as repetições anteriores."""
    grupos, identidades = defaultdict(list), set()
    for original in resultados:
        resultado = _normalizar_resultado(original)
        identidade = (resultado["config_id"], resultado["estrategia"], resultado.get("repeticao", 1))
        if identidade in identidades:
            raise ValueError(f"Repetição duplicada: {identidade}.")
        identidades.add(identidade)
        chave_grupo = (resultado["config_id"], resultado["estrategia"])
        if grupos[chave_grupo]:
            referencia = grupos[chave_grupo][0]
            for campo in ("elementos", "camadas", "resolucao", "seed", "transparencia", "cenario", "quantidade_gaussianas"):
                if referencia.get(campo) != resultado.get(campo):
                    raise ValueError(f"Repetições incompatíveis em {chave_grupo}: {campo} difere.")
        grupos[chave_grupo].append(resultado)
    agregados = []
    for (config_id, estrategia), itens in grupos.items():
        amostras = [amostra for item in itens for amostra in item["amostras_tempos"]]
        duracoes = [item.get("duracao_coleta_s", 0) for item in itens]
        total_s = sum(duracoes)
        agregados.append({
            "config_id": config_id, "estrategia": estrategia,
            "elementos": itens[0]["elementos"], "camadas": itens[0]["camadas"],
            "resolucao": itens[0]["resolucao"], "repeticoes": len(itens),
            "cenario": itens[0].get("cenario"), "quantidade_gaussianas": itens[0].get("quantidade_gaussianas"),
            **calcular_estatisticas(amostras),
            "std_medias_repeticoes_ms": statistics.pstdev(item["tempo_medio_ms"] for item in itens),
            "cpu_pct": (sum(item["cpu_pct"] * duracao for item, duracao in zip(itens, duracoes)) / total_s
                        if total_s > 0 else statistics.fmean(item["cpu_pct"] for item in itens)),
            "ram_mb": statistics.fmean(item["ram_mb"] for item in itens),
            "ram_max_mb": max(item.get("ram_max_mb", item["ram_mb"]) for item in itens),
            "amostras_tempos": amostras,
        })
    return agregados


def _resumo_serializavel(resultado):
    return {chave: valor for chave, valor in resultado.items() if not chave.startswith("amostras_")}


def _salvar_csv(caminho, linhas, campos=None):
    if campos is None:
        campos = list(linhas[0]) if linhas else []
    with Path(caminho).open("w", encoding="utf-8-sig", newline="") as arquivo:
        escritor = csv.DictWriter(arquivo, fieldnames=campos, extrasaction="raise")
        escritor.writeheader()
        escritor.writerows(linhas)


def exportar_resultados(resultados, pasta_saida, metadados=None):
    """Exporta dados brutos e resumos sem exigir GPU ou bibliotecas de gráficos."""
    if not resultados:
        raise ValueError("Nenhum resultado para exportar.")
    resultados = [_normalizar_resultado(resultado) for resultado in resultados]
    agregados = agregar_resultados(resultados)
    pasta = Path(pasta_saida)
    pasta.mkdir(parents=True, exist_ok=True)
    resumos = [_resumo_serializavel(resultado) for resultado in resultados]
    _salvar_csv(pasta / "resultados_benchmark.csv", resumos)
    _salvar_csv(pasta / "resumo_agregado.csv", [_resumo_serializavel(item) for item in agregados])
    amostras, recursos = [], []
    for resultado in resultados:
        identidade = {"config_id": resultado["config_id"], "estrategia": resultado["estrategia"],
                      "repeticao": resultado.get("repeticao", 1)}
        for frame, tempo_ms in enumerate(resultado["amostras_tempos"], start=1):
            amostras.append({**identidade, "frame": frame, "tempo_ms": float(tempo_ms)})
        for recurso in resultado.get("amostras_recursos", []):
            recursos.append({**identidade, **recurso})
    _salvar_csv(pasta / "amostras_frames.csv", amostras)
    _salvar_csv(pasta / "amostras_recursos.csv", recursos, [
        "config_id", "estrategia", "repeticao", "frame", "ram_mb", "cpu_pct_intervalo", "intervalo_s",
    ])
    documento = {"metadados": metadados or {}, "repeticoes": resumos,
                 "agregados": [_resumo_serializavel(item) for item in agregados]}
    for nome, conteudo in (("resumo.json", documento), ("metadados.json", metadados or {})):
        with (pasta / nome).open("w", encoding="utf-8") as arquivo:
            json.dump(conteudo, arquivo, indent=2, ensure_ascii=False, allow_nan=False)
    return agregados


def _gerar_graficos(agregados, pasta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    pasta.mkdir(parents=True, exist_ok=True)
    configs = list(dict.fromkeys(item["config_id"] for item in agregados))
    dados = {(item["config_id"], item["estrategia"]): item for item in agregados}
    cores = {"Monolítica": "#2563a6", "Multicamada": "#cf642c"}
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10})
    largura = max(8, len(configs) * 2.2)

    def barras(ax, campo, ylabel, titulo, alvo=None, erro=None):
        for numero, estrategia in enumerate(ESTRATEGIAS):
            presentes = [(i, dados[(config, estrategia)]) for i, config in enumerate(configs)
                         if (config, estrategia) in dados]
            x = [i + (numero - 0.5) * 0.36 for i, _ in presentes]
            alturas = [item[campo] for _, item in presentes]
            erros = [item[erro] for _, item in presentes] if erro else None
            ax.bar(x, alturas, width=0.34, yerr=erros, capsize=3,
                   color=cores[estrategia], label=estrategia)
        if alvo is not None:
            ax.axhline(alvo, linestyle="--", color="#666666", linewidth=1, label=f"Referência: {alvo:.2f}")
        ax.set_xticks(range(len(configs)), configs)
        ax.set(ylabel=ylabel, title=titulo, ylim=(0, None))
        ax.grid(axis="y", alpha=0.2)
        ax.set_axisbelow(True)
        ax.legend(fontsize=8)

    fig, ax = plt.subplots(figsize=(largura, 5), constrained_layout=True)
    barras(ax, "fps_medio", "FPS = 1000 / média de latência", "Vazão equivalente sem apresentação", 60)
    fig.savefig(pasta / "comparativo_fps.png", dpi=180)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(largura, 5), constrained_layout=True)
    barras(ax, "tempo_medio_ms", "Latência CPU + GPU (ms)", "Média ± desvio entre médias das repetições",
           ORCAMENTO_60FPS_MS, "std_medias_repeticoes_ms")
    fig.savefig(pasta / "comparativo_tempo_frame.png", dpi=180)
    plt.close(fig)
    fig, ax = plt.subplots(figsize=(largura, 5), constrained_layout=True)
    amostras, etiquetas, paleta = [], [], []
    for config in configs:
        for estrategia in ESTRATEGIAS:
            item = dados.get((config, estrategia))
            if item:
                amostras.append(item["amostras_tempos"])
                etiquetas.append(f"{config}\n{'Mono' if estrategia == 'Monolítica' else 'Multi'}")
                paleta.append(cores[estrategia])
    opcoes = {"patch_artist": True, "showfliers": True,
              "flierprops": {"markersize": 2, "alpha": 0.35}}
    try:
        box = ax.boxplot(amostras, tick_labels=etiquetas, **opcoes)
    except TypeError:
        box = ax.boxplot(amostras, labels=etiquetas, **opcoes)
    for patch, cor in zip(box["boxes"], paleta):
        patch.set_facecolor(cor)
    ax.axhline(ORCAMENTO_60FPS_MS, color="#666666", linestyle="--", linewidth=1)
    ax.set(ylabel="Latência CPU + GPU (ms)", title="Distribuição completa: outliers preservados")
    ax.grid(axis="y", alpha=0.2)
    ax.legend(handles=[Patch(color=cores[e], label=e) for e in ESTRATEGIAS], fontsize=8)
    fig.savefig(pasta / "distribuicao_tempo_frame.png", dpi=180)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(max(10, largura + 2), 5), constrained_layout=True)
    barras(axes[0], "cpu_pct", "CPU do processo (%)", "CPU sobre toda a coleta")
    barras(axes[1], "ram_mb", "RSS amostrada do processo (MiB)", "Memória residente média")
    fig.savefig(pasta / "comparativo_recursos.png", dpi=180)
    plt.close(fig)


def _gerar_relatorio(resultados, agregados, pasta, metadados):
    parametros = metadados.get("parametros", {})
    texto = [
        "# Relatório experimental de composição gráfica", "", "## Método", "",
        "Latência CPU + GPU em framebuffer offscreen RGBA8. Cada quadro inclui construção da geometria, "
        "envio dos comandos e `ctx.finish()`; não inclui simulação, coleta de recursos, PNG, eventos, troca de buffers ou V-Sync. "
        "Não corresponde ao tempo exclusivo da GPU nem à latência de apresentação na tela.", "",
        f"Aquecimento por execução: {parametros.get('frames_warmup', 'consultar metadados')} quadros; "
        f"coleta por repetição: {parametros.get('frames_medicao', 'consultar metadados')} quadros; "
        f"repetições: {parametros.get('repeticoes', 'consultar tabela')}; semente: {parametros.get('seed', 'consultar metadados')}. "
        "As estratégias recebem os mesmos snapshots com passo fixo de 1/60 s. A ordem alterna entre repetições.", "",
        f"Cenário: {parametros.get('cenario', 'consultar metadados')}; "
        f"cena 3D: {parametros.get('quantidade_gaussianas', 'consultar metadados')} gaussianas. "
        "A contagem de gaussianas é independente da carga sintética de retângulos dos presets.", "",
        "FPS é 1000 dividido pela média dos tempos. Percentis usam interpolação linear. Os agregados reúnem todas as amostras; "
        "o CSV por repetição permite examinar a variação entre execuções. As barras de erro mostram o desvio padrão "
        "entre médias das repetições, não um intervalo de confiança.", "",
        "CPU é a razão entre segundos de CPU do processo e tempo de parede de toda a coleta; pode exceder 100% em vários núcleos. "
        "O arquivo de recursos traz RSS amostrada e CPU em intervalos de pelo menos 100 ms quando disponíveis. "
        "RSS mede o processo completo, incluindo Python e caches do driver; não mede VRAM ou memória exclusiva de uma estratégia.", "",
        "## Resultados agregados", "",
        "| Config | Estratégia | Repetições | Quadros | Média (ms) | P95 (ms) | P99 (ms) | Máximo observado (ms) | FPS | Fora de 16,67 ms |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in agregados:
        texto.append(f"| {item['config_id']} | {item['estrategia']} | {item['repeticoes']} | {item['frames_medidos']} | "
                     f"{item['tempo_medio_ms']:.3f} | {item['tempo_p95_ms']:.3f} | {item['tempo_p99_ms']:.3f} | "
                     f"{item['tempo_max_ms']:.3f} | {item['fps_medio']:.2f} | {item['frames_fora_orcamento_pct']:.2f}% |")
    texto.extend(["", "## Comparação observada", ""])
    por_config = defaultdict(dict)
    for item in agregados:
        por_config[item["config_id"]][item["estrategia"]] = item
    for config, estrategias in por_config.items():
        if all(estrategia in estrategias for estrategia in ESTRATEGIAS):
            mono, multi = (estrategias[estrategia] for estrategia in ESTRATEGIAS)
            diferenca = 100 * (multi["tempo_medio_ms"] / mono["tempo_medio_ms"] - 1)
            relacao = "maior" if diferenca >= 0 else "menor"
            texto.append(f"- **{config}:** média multicamada {abs(diferenca):.2f}% {relacao} que a monolítica; "
                         f"P99 observado de {multi['tempo_p99_ms']:.3f} ms contra {mono['tempo_p99_ms']:.3f} ms. "
                         f"Quadros acima do orçamento: {multi['frames_fora_orcamento_pct']:.2f}% contra "
                         f"{mono['frames_fora_orcamento_pct']:.2f}%.")
    texto.extend([
        "", "## Limites da interpretação", "",
        "Os números descrevem somente a carga, o ambiente e a duração registrados. P95, P99 e máximo observado não são WCET "
        "nem garantias de prazo; zero violações observadas não assegura ausência futura. A separação em camadas, por si só, "
        "não demonstra melhor previsibilidade. Não foram avaliados escalonamento de tempo real, tolerância a falhas "
        "ou certificação aeronáutica. O aplicativo é uma demonstração acadêmica.", "",
        "Os testes usam a mesma sessão de processo/contexto, liberando recursos entre execuções; caches do driver, "
        "temperatura, frequência da GPU e atividade do sistema podem influenciar os resultados. Alternar a ordem reduz "
        "um possível viés, mas não substitui controle ambiental ou estudo estatístico de significância.", "",
        "## Arquivos para auditoria", "",
        "- `amostras_frames.csv`: uma linha por quadro, com configuração, estratégia e repetição.",
        "- `amostras_recursos.csv`: RSS e intervalos de CPU medidos fora da duração do quadro.",
        "- `resultados_benchmark.csv`: estatísticas de cada repetição; `resumo_agregado.csv`: agregados.",
        "- `resumo.json` e `metadados.json`: parâmetros, versões e identificação do ambiente OpenGL.",
        "- `graficos/`: FPS, médias, distribuição e recursos; `capturas/`: último quadro da primeira repetição.", "",
    ])
    (pasta / "relatorio_experimental.md").write_text("\n".join(texto), encoding="utf-8")


def gerar_graficos_e_relatorios(resultados, pasta_saida="resultados", metadados=None):
    pasta = Path(pasta_saida)
    agregados = exportar_resultados(resultados, pasta, metadados)
    _gerar_graficos(agregados, pasta / "graficos")
    _gerar_relatorio(resultados, agregados, pasta, metadados or {})
    return agregados


def _metadados(ctx, parametros, configuracoes):
    pacotes = {}
    for nome in ("moderngl", "glfw", "numpy", "matplotlib", "psutil", "Pillow"):
        try:
            pacotes[nome] = importlib.metadata.version(nome)
        except importlib.metadata.PackageNotFoundError:
            pacotes[nome] = "não identificado"
    return {
        "inicio_utc": datetime.now(timezone.utc).isoformat(), "python": sys.version,
        "executavel_python": sys.executable, "sistema": platform.platform(),
        "arquitetura": platform.machine(), "processador": platform.processor(), "cpu_logicas": os.cpu_count(),
        "opengl": {chave: ctx.info.get(chave) for chave in ("GL_VENDOR", "GL_RENDERER", "GL_VERSION", "GL_SHADING_LANGUAGE_VERSION")},
        "pacotes": pacotes, "parametros": parametros, "configuracoes": configuracoes,
        "metodo": {
            "alvo": "offscreen RGBA8; dimensão exata do preset; sem MSAA",
            "medida": "latência CPU + GPU sincronizada por ctx.finish por quadro",
            "inclui": ["construção de primitivas", "envio GL", "renderização", "composição", "ctx.finish"],
            "exclui": ["simulação", "geração de estresse", "recursos do processo", "PNG", "eventos", "swap/V-Sync"],
            "passo_simulacao_s": PASSO_SIMULACAO, "percentis": "interpolação linear inclusiva",
            "cpu": "100 * delta CPU processo / delta tempo de parede; coleta completa; pode exceder 100%",
            "ram": "RSS processo amostrada fora da duração do quadro; MiB; não mede VRAM",
            "ordem": "alternada por repetição e configuração", "nao_e_wcet": True,
        }, "ordem_execucao": [],
    }


def executar_benchmark_completo(
    frames_warmup=60, frames_medicao=300, repeticoes=3, pasta_saida="resultados",
    configs=None, transparencia=0.5, seed=42, cenario="incendio", quantidade_gaussianas=6000,
):
    """Executa a matriz em uma pasta única e retorna os resultados por repetição."""
    _inteiro(frames_warmup, "frames_warmup", 0)
    _inteiro(frames_medicao, "frames_medicao")
    _inteiro(repeticoes, "repeticoes")
    _inteiro(seed, "seed", 0)
    _inteiro(quantidade_gaussianas, "quantidade_gaussianas")
    if cenario not in CENARIOS:
        raise ValueError(f"Cenário inválido: {cenario}.")
    if isinstance(transparencia, bool) or not math.isfinite(transparencia) or not 0 <= transparencia <= 1:
        raise ValueError("transparencia deve estar entre 0 e 1.")
    configuracoes = _configuracoes_selecionadas(configs)
    parametros = {"frames_warmup": frames_warmup, "frames_medicao": frames_medicao,
                  "repeticoes": repeticoes, "transparencia": transparencia, "seed": seed,
                  "cenario": cenario, "quantidade_gaussianas": quantidade_gaussianas}
    identificador = datetime.now(timezone.utc).strftime("execucao_%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
    pasta = Path(pasta_saida).resolve() / identificador
    pasta.mkdir(parents=True, exist_ok=False)
    import glfw
    import moderngl

    janela = ctx = None
    resultados = []
    metadados = {"parametros": parametros, "configuracoes": configuracoes}
    try:
        if not glfw.init():
            raise RuntimeError("Não foi possível inicializar GLFW.")
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.VISIBLE, False)
        janela = glfw.create_window(64, 64, "Benchmark offscreen", None, None)
        if not janela:
            raise RuntimeError("Não foi possível criar o contexto OpenGL 3.3 para o benchmark.")
        glfw.make_context_current(janela)
        glfw.swap_interval(0)
        ctx = moderngl.create_context(require=330)
        metadados = _metadados(ctx, parametros, configuracoes)
        print(f"Benchmark: {len(configuracoes)} configurações × 2 estratégias × {repeticoes} repetições.")
        print(f"Saída: {pasta}")
        for indice_config, config in enumerate(configuracoes):
            dados = _sequencia_dados(frames_warmup + frames_medicao, seed, cenario)
            for repeticao in range(1, repeticoes + 1):
                estrategias = ESTRATEGIAS if (repeticao - 1 + indice_config) % 2 == 0 else ESTRATEGIAS[::-1]
                for estrategia in estrategias:
                    print(f"{config['id']} | {estrategia} | repetição {repeticao}/{repeticoes}", flush=True)
                    metadados["ordem_execucao"].append({"config_id": config["id"], "repeticao": repeticao, "estrategia": estrategia})
                    captura = (pasta / "capturas" / f"{config['id']}_{'mono' if estrategia == 'Monolítica' else 'multi'}.png"
                               if repeticao == 1 else None)
                    resultado = executar_teste_configuracao(
                        ctx, janela, config, estrategia, frames_warmup, frames_medicao, transparencia,
                        repeticao=repeticao, seed=seed, cenario=cenario, quantidade_gaussianas=quantidade_gaussianas,
                        sequencia_dados=dados, caminho_captura=captura,
                    )
                    resultados.append(resultado)
                    print(f"  média {resultado['tempo_medio_ms']:.3f} ms | P99 {resultado['tempo_p99_ms']:.3f} ms | "
                          f"{resultado['fps_medio']:.1f} FPS", flush=True)
        metadados["estado"] = "concluido"
    except BaseException as erro:
        metadados["estado"] = "interrompido"
        metadados["erro"] = f"{type(erro).__name__}: {erro}"
        if resultados:
            exportar_resultados(resultados, pasta, metadados)
        else:
            (pasta / "metadados.json").write_text(json.dumps(metadados, indent=2, ensure_ascii=False), encoding="utf-8")
        raise
    finally:
        with ExitStack() as liberacoes:
            liberacoes.callback(glfw.terminate)
            if janela is not None:
                liberacoes.callback(glfw.destroy_window, janela)
            if ctx is not None:
                liberacoes.callback(ctx.release)
    metadados["fim_utc"] = datetime.now(timezone.utc).isoformat()
    gerar_graficos_e_relatorios(resultados, pasta, metadados)
    print(f"Concluído. Amostras, metadados, gráficos e relatório em: {pasta}")
    return resultados


def criar_parser():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--warmup", type=int, default=60, help="quadros descartados por execução (padrão: 60)")
    parser.add_argument("--frames", type=int, default=300, help="quadros medidos por repetição (padrão: 300)")
    parser.add_argument("--repeticoes", type=int, default=3, help="repetições por estratégia (padrão: 3)")
    parser.add_argument("--saida", default="resultados", help="pasta base; cada execução cria uma subpasta única")
    parser.add_argument("--configs", nargs="+", choices=[config["id"] for config in CONFIGURACOES_EXPERIMENTAIS],
                        help="presets da matriz (padrão: C1 C2 C3 C4)")
    parser.add_argument("--transparencia", type=float, default=0.5, help="fração de elementos transparentes (0 a 1)")
    parser.add_argument("--seed", type=int, default=42, help="semente reprodutível (padrão: 42)")
    parser.add_argument("--cenario", choices=CENARIOS, default="incendio", help="cenário da missão (padrão: incendio)")
    parser.add_argument("--gaussianas", type=int, default=6000, help="quantidade de gaussianas 3D, independente dos presets (padrão: 6000)")
    return parser


def main(argv=None):
    parser = criar_parser()
    argumentos = parser.parse_args(argv)
    try:
        executar_benchmark_completo(
            frames_warmup=argumentos.warmup, frames_medicao=argumentos.frames,
            repeticoes=argumentos.repeticoes, pasta_saida=argumentos.saida,
            configs=argumentos.configs, transparencia=argumentos.transparencia, seed=argumentos.seed,
            cenario=argumentos.cenario, quantidade_gaussianas=argumentos.gaussianas,
        )
    except (ValueError, RuntimeError) as erro:
        parser.exit(1, f"Benchmark não concluído: {erro}\n")
    except KeyboardInterrupt:
        parser.exit(130, "Benchmark interrompido. Repetições completas foram preservadas.\n")


if __name__ == "__main__":
    main()
