"""Contratos científicos/exportação: não abrem janela nem inicializam OpenGL."""

import csv
import json
import math
from pathlib import Path
import tempfile
import unittest

from benchmark import (
    ORCAMENTO_60FPS_MS, _gerar_relatorio, _liberar_recursos, _sequencia_dados,
    agregar_resultados, calcular_estatisticas, criar_parser,
    executar_benchmark_completo, exportar_resultados, validar_amostras,
)
from configuracoes import obter_configuracoes, validar_configuracao


def fixture_resultado(tempos=(10.0, 20.0, 30.0), repeticao=1, estrategia="Monolítica", config_id="C1"):
    return {
        "config_id": config_id, "elementos": 1000, "camadas": 2,
        "resolucao": "1280x720", "estrategia": estrategia, "repeticao": repeticao,
        "seed": 42, "frames_warmup": 2, "transparencia": 0.5,
        "cenario": "incendio", "quantidade_gaussianas": 6000,
        **calcular_estatisticas(tempos), "cpu_pct": 50.0, "duracao_coleta_s": 1.0,
        "ram_mb": 100.0, "ram_max_mb": 110.0, "amostras_tempos": list(tempos),
        "amostras_recursos": [{"frame": len(tempos), "ram_mb": 100.0,
                              "cpu_pct_intervalo": 50.0, "intervalo_s": 0.5}],
    }


class EstatisticasTests(unittest.TestCase):
    def test_formula_fps_percentis_e_desvio(self):
        dados = calcular_estatisticas([1, 2, 3, 4])
        self.assertEqual(dados["tempo_medio_ms"], 2.5)
        self.assertEqual(dados["fps_medio"], 400.0)
        self.assertAlmostEqual(dados["tempo_std_ms"], math.sqrt(1.25))
        self.assertEqual(dados["tempo_mediana_ms"], 2.5)
        self.assertAlmostEqual(dados["tempo_p95_ms"], 3.85)
        self.assertAlmostEqual(dados["tempo_p99_ms"], 3.97)
        self.assertEqual(dados["tempo_max_ms"], 4)

    def test_conta_frames_acima_do_orcamento_sem_arredondar(self):
        dados = calcular_estatisticas([10, ORCAMENTO_60FPS_MS, 20, 30])
        self.assertEqual(dados["frames_fora_orcamento"], 2)
        self.assertEqual(dados["frames_fora_orcamento_pct"], 50.0)
        self.assertEqual(dados["frames_medidos"], 4)

    def test_uma_amostra_e_iteradores(self):
        dados = calcular_estatisticas(iter([20]))
        self.assertEqual(dados["tempo_std_ms"], 0)
        self.assertEqual(dados["tempo_p99_ms"], 20)
        self.assertEqual(dados["fps_medio"], 50)

    def test_rejeita_amostras_invalidas(self):
        for caso in ([], [0], [-1], [math.nan], [math.inf], [None], ["10"], [True]):
            with self.subTest(caso=caso), self.assertRaises(ValueError):
                validar_amostras(caso)

    def test_rejeita_orcamentos_invalidos(self):
        for orcamento in (0, -1, math.nan, math.inf, True):
            with self.subTest(orcamento=orcamento), self.assertRaises(ValueError):
                calcular_estatisticas([10], orcamento)

    def test_agregado_pondera_todos_os_frames(self):
        primeira = fixture_resultado([10], repeticao=1)
        segunda = fixture_resultado([20, 30], repeticao=2)
        primeira.update(cpu_pct=25, duracao_coleta_s=1)
        segunda.update(cpu_pct=100, duracao_coleta_s=2)
        agregado, = agregar_resultados([primeira, segunda])
        self.assertEqual(agregado["repeticoes"], 2)
        self.assertEqual(agregado["frames_medidos"], 3)
        self.assertEqual(agregado["tempo_medio_ms"], 20)
        self.assertEqual(agregado["fps_medio"], 50)
        self.assertEqual(agregado["cpu_pct"], 75)
        self.assertEqual(agregado["amostras_tempos"], [10, 20, 30])

    def test_repeticao_duplicada_nao_e_sobrescrita(self):
        with self.assertRaises(ValueError):
            agregar_resultados([fixture_resultado(), fixture_resultado()])

    def test_nao_agrega_cargas_ou_cenarios_diferentes(self):
        for campo, valor in (("quantidade_gaussianas", 12000), ("cenario", "normal"), ("seed", 7), ("elementos", 2000)):
            primeira, segunda = fixture_resultado(), fixture_resultado(repeticao=2)
            segunda[campo] = valor
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                agregar_resultados([primeira, segunda])

    def test_resumo_recalculado_a_partir_das_amostras(self):
        resultado = fixture_resultado([10, 20])
        resultado["tempo_medio_ms"] = -1
        resultado["fps_medio"] = 0
        resultado["amostras_tempos"] = iter([10, 20])
        agregado, = agregar_resultados([resultado])
        self.assertEqual(agregado["tempo_medio_ms"], 15)
        self.assertAlmostEqual(agregado["fps_medio"], 1000 / 15)


class ExportacaoTests(unittest.TestCase):
    def test_csv_json_preservam_repeticoes_e_amostras(self):
        resultados = [fixture_resultado(repeticao=1), fixture_resultado([2, 4], repeticao=2)]
        with tempfile.TemporaryDirectory() as temporaria:
            pasta = Path(temporaria)
            exportar_resultados(resultados, pasta, {"seed": 42})
            with (pasta / "resultados_benchmark.csv").open(encoding="utf-8-sig", newline="") as arquivo:
                resumo = list(csv.DictReader(arquivo))
            with (pasta / "amostras_frames.csv").open(encoding="utf-8-sig", newline="") as arquivo:
                frames = list(csv.DictReader(arquivo))
            self.assertEqual(len(resumo), 2)
            self.assertEqual(len(frames), 5)
            self.assertEqual([linha["frame"] for linha in frames], ["1", "2", "3", "1", "2"])
            self.assertEqual({linha["repeticao"] for linha in frames}, {"1", "2"})
            self.assertEqual(resumo[0]["estrategia"], "Monolítica")
            documento = json.loads((pasta / "resumo.json").read_text(encoding="utf-8"))
            self.assertEqual(documento["metadados"], {"seed": 42})
            self.assertEqual(len(documento["repeticoes"]), 2)
            self.assertEqual(documento["agregados"][0]["frames_medidos"], 5)
            self.assertNotIn("amostras_tempos", documento["repeticoes"][0])

    def test_csv_escapa_virgula_em_identificador(self):
        with tempfile.TemporaryDirectory() as temporaria:
            exportar_resultados([fixture_resultado(config_id="teste, personalizado")], temporaria)
            with (Path(temporaria) / "amostras_frames.csv").open(encoding="utf-8-sig", newline="") as arquivo:
                self.assertEqual(next(csv.DictReader(arquivo))["config_id"], "teste, personalizado")

    def test_relatorio_analisa_dados_sem_conclusao_predefinida(self):
        resultados = [fixture_resultado([10, 10]), fixture_resultado([20, 20], estrategia="Multicamada")]
        with tempfile.TemporaryDirectory() as temporaria:
            pasta = Path(temporaria)
            agregados = exportar_resultados(resultados, pasta)
            _gerar_relatorio(resultados, agregados, pasta, {})
            texto = (pasta / "relatorio_experimental.md").read_text(encoding="utf-8")
            self.assertIn("100.00% maior", texto)
            self.assertIn("não são WCET", texto)
            self.assertIn("não demonstra melhor previsibilidade", texto)
            self.assertIn("não mede VRAM", texto)

    def test_exportacao_vazia_rejeitada(self):
        with tempfile.TemporaryDirectory() as temporaria, self.assertRaises(ValueError):
            exportar_resultados([], temporaria)


class ConfiguracaoTests(unittest.TestCase):
    def test_presets_da_matriz_sao_copias(self):
        configs = obter_configuracoes()
        self.assertEqual([config["elementos"] for config in configs], [1000, 10000, 50000, 100000])
        self.assertEqual([config["camadas"] for config in configs], [2, 2, 4, 4])
        configs[0]["elementos"] = 0
        self.assertEqual(obter_configuracoes(["C1"])[0]["elementos"], 1000)
        self.assertEqual([config["id"] for config in obter_configuracoes(["c4", "c1"])], ["C4", "C1"])

    def test_presets_invalidos_rejeitados(self):
        for ids in ([], ["C5"], ["C1", "C1"]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                obter_configuracoes(ids)
        for campo, valor in (("camadas", 3), ("largura", 0), ("elementos", -1), ("altura", True)):
            config = obter_configuracoes("C1")[0]
            config[campo] = valor
            with self.subTest(campo=campo), self.assertRaises(ValueError):
                validar_configuracao(config)

    def test_argumentos_invalidos_falham_antes_de_inicializar_gpu(self):
        for argumentos in ({"frames_warmup": -1}, {"frames_medicao": 0}, {"repeticoes": 0},
                           {"transparencia": 1.1}, {"seed": -1}, {"configs": []},
                           {"cenario": "inexistente"}, {"quantidade_gaussianas": 0}):
            with self.subTest(argumentos=argumentos), self.assertRaises(ValueError):
                executar_benchmark_completo(**argumentos)

    def test_cli_configuravel(self):
        args = criar_parser().parse_args(["--warmup", "5", "--frames", "30", "--repeticoes", "2", "--configs", "C1", "C4", "--cenario", "trafego", "--gaussianas", "12000"])
        self.assertEqual((args.warmup, args.frames, args.repeticoes, args.configs), (5, 30, 2, ["C1", "C4"]))
        self.assertEqual((args.cenario, args.gaussianas), ("trafego", 12000))

    def test_dados_sao_reprodutiveis_e_preservam_snapshots(self):
        primeira = _sequencia_dados(5, 42)
        segunda = _sequencia_dados(5, 42)
        self.assertEqual(primeira, segunda)
        self.assertNotEqual(primeira, _sequencia_dados(5, 43))
        self.assertNotEqual(primeira, _sequencia_dados(5, 42, "normal"))
        primeira[0]["mensagens_alerta"].append("teste")
        self.assertNotIn("teste", primeira[1]["mensagens_alerta"])

    def test_libera_todos_os_objetos_apesar_de_falha(self):
        chamadas = []

        class Recurso:
            def __init__(self, nome, falha=False):
                self.nome, self.falha = nome, falha

            def release(self):
                chamadas.append(self.nome)
                if self.falha:
                    raise RuntimeError("falha de teste")

        with self.assertRaises(RuntimeError):
            _liberar_recursos(Recurso("destino", True), Recurso("textura"), Recurso("pipeline"))
        self.assertEqual(chamadas, ["destino", "textura", "pipeline"])


if __name__ == "__main__":
    unittest.main()
