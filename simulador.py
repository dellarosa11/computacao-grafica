"""Telemetria determinística para a missão de reconhecimento aéreo.

Um mesmo seed e a mesma sequência de passos produzem os mesmos dados,
independentemente da velocidade da GPU ou da estratégia de composição.
"""

import math
import random
import time


class SimuladorVoo:
    CENARIOS = ("normal", "trafego", "incendio")

    def __init__(self, seed=42, cenario="normal"):
        self.seed = seed
        self.cenario = "normal"
        self.reiniciar(cenario=cenario)

    def reiniciar(self, seed=None, cenario=None):
        """Recomeça missão e RNG, preservando cenário quando omitido."""
        if seed is not None:
            self.seed = seed
        self._rng = random.Random(self.seed)
        self.tempo_inicio = time.perf_counter()
        self.tempo_anterior = self.tempo_inicio
        self.tempo = 0.0
        self._fase = 0.0
        self.altitude = 8500.0
        self.velocidade = 280.0
        self.rumo = 120.0
        self.pitch = 2.5
        self.roll = 0.0
        self.vertical_speed = 350.0
        self.temperatura_oleo = 52.0
        self.pressao_oleo = 48.0
        self.n1_rpm = 84.5
        self.egt = 610.0
        self.combustivel = 4500.0
        self.distancia_waypoint = 14.8
        self.nome_waypoint = "BRS01"
        self.trajetoria_pontos = [
            (-0.4, -0.3), (-0.2, -0.1), (0.0, 0.2), (0.3, 0.5), (0.5, 0.8)
        ]
        self._alvos_base = [
            (-0.3, 0.4, "+12"), (0.5, 0.2, "-08"),
            (0.1, -0.5, "+24"), (-0.6, -0.2, "-15"),
        ]
        self.tcas_alvos = []
        self.mensagens_alerta = []
        self.definir_cenario(self.cenario if cenario is None else cenario)

    def definir_cenario(self, cenario):
        """Seleciona um cenário sem consumir números aleatórios."""
        cenario = str(cenario).strip().lower()
        cenario = {"tráfego": "trafego", "incêndio": "incendio"}.get(cenario, cenario)
        if cenario not in self.CENARIOS:
            raise ValueError("Cenário deve ser normal, trafego ou incendio.")
        self.cenario = cenario
        self._atualizar_alertas()
        self._atualizar_alvos()

    def _atualizar_alvos(self):
        self.tcas_alvos = [
            {
                "x": x + 0.025 * math.sin(self.tempo * 0.18 + i),
                "y": y + 0.025 * math.sin(self.tempo * 0.13 + i),
                "rel_alt": altitude,
                "alerta": self.cenario == "trafego" and i == 1,
            }
            for i, (x, y, altitude) in enumerate(self._alvos_base)
        ]

    def _atualizar_alertas(self):
        self.mensagens_alerta = []
        self.nivel_alerta = 0
        self.estado_sistema = "SYS NORMAL"
        if self.cenario == "trafego":
            self.nivel_alerta = 1
            self.estado_sistema = "TRAFEGO PROXIMO"
            self.mensagens_alerta.append("TCAS: TRAFFIC ADVISORY")
        elif self.cenario == "incendio":
            self.nivel_alerta = 2
            self.estado_sistema = "FOCOS DE CALOR DETECTADOS"
            self.mensagens_alerta.extend(["ALERTA: INCENDIO FLORESTAL", "SENSOR IR: 3 FOCOS ATIVOS"])
        if self.temperatura_oleo > 70.0:
            self.nivel_alerta = 2
            self.estado_sistema = "ENG 1 OIL TEMP HIGH"
            self.mensagens_alerta.append("WARNING: ENG 1 OIL TEMP HIGH")
        elif self.temperatura_oleo > 62.0:
            self.nivel_alerta = max(1, self.nivel_alerta)
            if self.cenario == "normal":
                self.estado_sistema = "CAUTION: OIL TEMP ADVISORY"
            self.mensagens_alerta.append("CAUTION: OIL TEMP ADVISORY")

    def atualizar(self, dt=None):
        """Avança em segundos; dt=0 pausa inclusive o estado aleatório.

        Passos explícitos não são truncados. O benchmark pode comparar o
        mesmo instante simulado nas duas estratégias. Sem passo explícito,
        usa relógio monotônico, imune a ajustes no relógio civil.
        """
        agora = time.perf_counter()
        if dt is None:
            dt = agora - self.tempo_anterior
        dt = float(dt)
        if not math.isfinite(dt) or dt < 0:
            raise ValueError("dt deve ser um número finito e não negativo.")
        self.tempo_anterior = agora
        if dt == 0:
            return

        self.tempo += dt
        self._fase = self.tempo * 0.8
        fase = self._fase
        # Difusão proporcional a sqrt(dt); não há RNG por frame pausado.
        ruido = math.sqrt(dt)
        self.pitch = 3.0 * math.sin(fase * 0.7) + self._rng.uniform(-0.35, 0.35) * ruido
        self.roll = 8.0 * math.sin(fase * 0.4) + self._rng.uniform(-0.5, 0.5) * ruido
        self.vertical_speed = 300.0 * math.sin(fase * 0.7) + self._rng.uniform(-30, 30) * ruido
        self.altitude += self.vertical_speed / 60.0 * dt
        self.velocidade += 1.5 * math.cos(fase * 0.5) * dt + self._rng.uniform(-0.4, 0.4) * ruido
        self.velocidade = max(180.0, min(340.0, self.velocidade))
        self.rumo = (self.rumo + 1.2 * math.sin(fase * 0.3) * dt) % 360.0
        self.temperatura_oleo = max(40.0, min(85.0, self.temperatura_oleo + self._rng.uniform(-0.12, 0.12) * ruido))
        self.n1_rpm = 84.0 + 3.0 * math.sin(fase * 0.5)
        self.egt = 600.0 + 15.0 * math.sin(fase * 0.5)
        self.combustivel = max(0.0, self.combustivel - 0.2 * dt)
        self.distancia_waypoint = max(0.5, self.distancia_waypoint - self.velocidade / 3600 * dt)
        self._atualizar_alertas()
        self._atualizar_alvos()

    def obter_dados(self):
        """Retorna cópia da telemetria sem referências mutáveis internas."""
        return {
            "altitude": round(self.altitude, 1),
            "velocidade": round(self.velocidade, 1),
            "rumo": round(self.rumo, 1),
            "pitch": round(self.pitch, 2),
            "roll": round(self.roll, 2),
            "vertical_speed": round(self.vertical_speed, 1),
            "temperatura_oleo": round(self.temperatura_oleo, 1),
            "pressao_oleo": round(self.pressao_oleo, 1),
            "n1_rpm": round(self.n1_rpm, 1),
            "egt": round(self.egt, 1),
            "combustivel": round(self.combustivel, 1),
            "estado": self.estado_sistema,
            "nivel_alerta": self.nivel_alerta,
            "mensagens_alerta": list(self.mensagens_alerta),
            "distancia_waypoint": round(self.distancia_waypoint, 1),
            "nome_waypoint": self.nome_waypoint,
            "trajetoria_pontos": list(self.trajetoria_pontos),
            "tcas_alvos": [dict(alvo) for alvo in self.tcas_alvos],
            "nome_missao": "SENTINELA / RECONHECIMENTO AEREO",
            "cenario": self.cenario,
            "tempo": self.tempo,
            "focos_detectados": 3 if self.cenario == "incendio" else 0,
            "temperatura_foco": round(386.0 + 12.0 * math.sin(self.tempo * 0.3), 1) if self.cenario == "incendio" else 24.0,
            "bateria": round(max(0.0, 98.0 - self.tempo / 180), 1),
            "area_monitorada": round(2.4 + self.tempo * 0.003, 2),
        }
