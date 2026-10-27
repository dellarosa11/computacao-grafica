"""Splatting de Gaussianas 3D para monitoramento aéreo de terreno sintético.

Pipeline: centros/covariâncias em mundo -> câmera -> projeção perspectiva e
Jacobiana -> descarte de splats invisíveis -> ordem estável do fundo para a
frente -> quads instanciados com densidade Gaussiana no fragment shader.
As funções de geração e projeção são independentes de OpenGL.
"""

from dataclasses import dataclass
import math
import time

import numpy as np


@dataclass(frozen=True)
class ProjecaoGaussianas:
    centros_ndc: np.ndarray
    covariancias_ndc: np.ndarray
    cores: np.ndarray
    profundidades: np.ndarray
    indices: np.ndarray

    def __len__(self):
        return len(self.indices)


def matriz_camera(posicao, alvo=(0.0, 0.3, 0.0), cima=(0.0, 1.0, 0.0)):
    """Matriz view right-handed, com câmera olhando na direção de -Z."""
    posicao, alvo, cima = (np.asarray(v, dtype=np.float64) for v in (posicao, alvo, cima))
    if any(v.shape != (3,) or not np.isfinite(v).all() for v in (posicao, alvo, cima)):
        raise ValueError("Posição, alvo e vetor cima devem conter três valores finitos.")
    z = posicao - alvo
    if np.linalg.norm(z) < 1e-10:
        raise ValueError("A posição da câmera deve ser diferente do alvo.")
    z /= np.linalg.norm(z)
    x = np.cross(cima, z)
    if np.linalg.norm(x) < 1e-10:
        raise ValueError("O vetor cima não pode ser paralelo à direção da câmera.")
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    view = np.eye(4, dtype=np.float64)
    view[:3, :3] = np.stack([x, y, z])
    view[:3, 3] = -view[:3, :3] @ posicao
    return view


def projetar_gaussianas(centros, covariancias, cores, view=None, *, fov_y=48.0,
                       aspecto=1.6, near=0.1, far=100.0, sigmas=3.0):
    """Projeta Gaussianas anisotrópicas usando C2D = J R C3D Rᵀ Jᵀ.

    Centros (N,3) e covariâncias (N,3,3) estão em coordenadas de mundo;
    cores (N,4) usam RGBA linear sem pré-multiplicação. ``view`` é uma
    matriz afim (4,4), identidade por padrão. FOV vertical em graus;
    ``aspecto`` é largura/altura. Resultados usam NDC [-1,1].

    A ordem retornada é back-to-front estável: profundidades iguais
    preservam a ordem de entrada. A elipse de suporte, com raio de 3σ,
    participa do teste de frustum para evitar desaparecimentos nas bordas.
    Centros atrás de near ou além de far, dados não finitos e covariâncias
    não positivas são descartados antes da divisão perspectiva.
    """
    centros = np.asarray(centros, dtype=np.float64)
    covariancias = np.asarray(covariancias, dtype=np.float64)
    cores = np.asarray(cores, dtype=np.float64)
    n = len(centros)
    if centros.shape != (n, 3) or covariancias.shape != (n, 3, 3) or cores.shape != (n, 4):
        raise ValueError("Esperados centros (N,3), covariâncias (N,3,3), cores (N,4).")
    parametros = np.array([fov_y, aspecto, near, far, sigmas], dtype=np.float64)
    if not np.isfinite(parametros).all() or not (0 < fov_y < 179 and aspecto > 0 and 0 < near < far and sigmas > 0):
        raise ValueError("Parâmetros de câmera inválidos.")
    view = np.eye(4, dtype=np.float64) if view is None else np.asarray(view, dtype=np.float64)
    if view.shape != (4, 4) or not np.isfinite(view).all() or not np.allclose(view[3], [0, 0, 0, 1]):
        raise ValueError("view deve ser uma matriz afim finita (4,4).")

    rotacao = view[:3, :3]
    camera = centros @ rotacao.T + view[:3, 3]
    profundidades = -camera[:, 2]
    valido = ((profundidades >= near) & (profundidades <= far)
              & np.isfinite(camera).all(axis=1)
              & np.isfinite(covariancias).all(axis=(1, 2))
              & np.isfinite(cores).all(axis=1) & (cores[:, 3] > 0))
    indices = np.flatnonzero(valido)
    camera = camera[indices]
    profundidades = profundidades[indices]
    cov = covariancias[indices]
    # Covariâncias devem ser simétricas e sem autovalores negativos.
    cov = (cov + cov.transpose(0, 2, 1)) * 0.5
    positivas = np.linalg.eigvalsh(cov).min(axis=1) >= -1e-12
    indices, camera, profundidades, cov = (
        indices[positivas], camera[positivas], profundidades[positivas], cov[positivas]
    )
    fy = 1.0 / math.tan(math.radians(fov_y) * 0.5)
    fx = fy / aspecto
    d = profundidades
    centros_ndc = camera[:, :2] * np.array([fx, fy]) / d[:, None]
    jacobiana = np.zeros((len(indices), 2, 3), dtype=np.float64)
    jacobiana[:, 0, 0] = fx / d
    jacobiana[:, 1, 1] = fy / d
    jacobiana[:, 0, 2] = fx * camera[:, 0] / d**2
    jacobiana[:, 1, 2] = fy * camera[:, 1] / d**2
    cov_camera = rotacao[None] @ cov @ rotacao.T[None]
    cov_ndc = jacobiana @ cov_camera @ jacobiana.transpose(0, 2, 1)
    cov_ndc = (cov_ndc + cov_ndc.transpose(0, 2, 1)) * 0.5
    raios = sigmas * np.sqrt(np.maximum(cov_ndc[:, (0, 1), (0, 1)], 0))
    visivel = ((centros_ndc + raios >= -1).all(axis=1)
               & (centros_ndc - raios <= 1).all(axis=1)
               & np.isfinite(cov_ndc).all(axis=(1, 2)))
    indices = indices[visivel]
    ordem = np.argsort(-profundidades[visivel], kind="stable")
    return ProjecaoGaussianas(
        centros_ndc[visivel][ordem], cov_ndc[visivel][ordem],
        np.clip(cores[indices][ordem], 0.0, 1.0),
        profundidades[visivel][ordem], indices[ordem],
    )


def _altura_terreno(x, z):
    return (0.16 + 1.35 * np.exp(-((x + 1.5)**2 / 3.8 + (z + 0.8)**2 / 6.0))
            + 0.95 * np.exp(-((x - 2.3)**2 / 2.1 + (z - 1.8)**2 / 3.0))
            + 0.14 * np.sin(x * 1.5 + z * 0.8)
            + 0.09 * np.cos(z * 2.0 - x * 0.5))


def gerar_cena_sintetica(quantidade=6000, seed=42):
    """Retorna centros, covariâncias, RGBA e tipo (0 terreno, 1 fumaça, 2 fogo).

    O terreno é uma malha estratificada de Gaussianas inclinadas conforme a
    superfície; três focos geram plumas volumétricas. Nenhum dado externo ou
    reconstrução fotogramétrica é usado: trata-se de uma cena sintética.
    """
    quantidade = int(quantidade)
    if quantidade < 1:
        raise ValueError("A quantidade deve ser positiva.")
    rng = np.random.default_rng(seed)
    n_terreno = max(1, int(quantidade * 0.86))
    n_fumaca = int((quantidade - n_terreno) * 0.72)
    n_fogo = quantidade - n_terreno - n_fumaca
    centros = np.empty((quantidade, 3), dtype=np.float64)
    cov = np.zeros((quantidade, 3, 3), dtype=np.float64)
    cores = np.empty((quantidade, 4), dtype=np.float64)
    tipos = np.zeros(quantidade, dtype=np.uint8)
    colunas = int(np.ceil(np.sqrt(n_terreno * 1.25)))
    linhas = int(np.ceil(n_terreno / colunas))
    ix, iz = np.arange(n_terreno) % colunas, np.arange(n_terreno) // colunas
    x = ((ix + 0.5 + rng.uniform(-0.32, 0.32, n_terreno)) / colunas - 0.5) * 10
    z = ((iz + 0.5 + rng.uniform(-0.32, 0.32, n_terreno)) / linhas - 0.5) * 8
    y = _altura_terreno(x, z)
    centros[:n_terreno] = np.column_stack([x, y, z])
    dx = (_altura_terreno(x + 0.01, z) - _altura_terreno(x - 0.01, z)) / 0.02
    dz = (_altura_terreno(x, z + 0.01) - _altura_terreno(x, z - 0.01)) / 0.02
    escala = np.sqrt(80 / n_terreno) * 0.72
    base = np.zeros((n_terreno, 3, 3), dtype=np.float64)
    base[:, 0, 0] = escala
    base[:, 1, 0] = dx * escala
    base[:, 1, 1] = escala * 0.25
    base[:, 1, 2] = dz * escala
    base[:, 2, 2] = escala
    cov[:n_terreno] = base @ base.transpose(0, 2, 1)
    elevacao = np.clip(y / 1.7, 0, 1)
    verde = np.array([0.12, 0.29, 0.18])
    rocha = np.array([0.48, 0.48, 0.34])
    rgb = verde[None] * (1 - elevacao[:, None] * 0.7) + rocha[None] * elevacao[:, None] * 0.7
    luz = np.clip(0.95 - 0.36 * dx - 0.23 * dz, 0.55, 1.2)
    rgb *= luz[:, None] * rng.uniform(0.78, 1.12, (n_terreno, 1))
    # Leito do rio: faixa sinuosa azul, integrada ao mesmo conjunto 3D.
    rio = np.abs(x - (0.7 * np.sin(z * 0.9) - 2.4)) < 0.12
    rgb[rio] = np.array([0.10, 0.35, 0.44]) * luz[rio, None]
    cores[:n_terreno, :3] = rgb
    cores[:n_terreno, 3] = 0.98

    focos = np.array([[1.45, -0.7], [0.4, 1.4], [2.8, 0.5]])
    if n_fumaca:
        ini, fim = n_terreno, n_terreno + n_fumaca
        foco = focos[np.arange(n_fumaca) % 3]
        altura = rng.uniform(0.12, 2.7, n_fumaca)
        dispersao = 0.06 + altura * 0.16
        px = foco[:, 0] + altura * 0.23 + rng.normal(0, dispersao)
        pz = foco[:, 1] + rng.normal(0, dispersao)
        py = _altura_terreno(foco[:, 0], foco[:, 1]) + altura
        centros[ini:fim] = np.column_stack([px, py, pz])
        sigma = 0.10 + altura * 0.10
        cov[ini:fim, 0, 0] = sigma**2
        cov[ini:fim, 1, 1] = (sigma * 1.4)**2
        cov[ini:fim, 2, 2] = sigma**2
        cinza = rng.uniform(0.18, 0.37, (n_fumaca, 1))
        cores[ini:fim, :3] = cinza * np.array([[0.94, 1.0, 1.06]])
        cores[ini:fim, 3] = rng.uniform(0.07, 0.18, n_fumaca)
        tipos[ini:fim] = 1
    if n_fogo:
        ini = n_terreno + n_fumaca
        foco = focos[np.arange(n_fogo) % 3]
        px = foco[:, 0] + rng.normal(0, 0.13, n_fogo)
        pz = foco[:, 1] + rng.normal(0, 0.14, n_fogo)
        py = _altura_terreno(px, pz) + rng.uniform(0.03, 0.29, n_fogo)
        centros[ini:] = np.column_stack([px, py, pz])
        cov[ini:, 0, 0] = 0.055**2
        cov[ini:, 1, 1] = 0.14**2
        cov[ini:, 2, 2] = 0.055**2
        cores[ini:, 0] = 1.0
        cores[ini:, 1] = rng.uniform(0.22, 0.74, n_fogo)
        cores[ini:, 2] = 0.03
        cores[ini:, 3] = 0.80
        tipos[ini:] = 2
    return centros, cov, cores, tipos


def _empacotar_instancias(projecao, tamanho):
    """Converte covariâncias em eixos de elipse e em dez floats por splat."""
    if not len(projecao):
        return np.empty((0, 10), dtype="f4")
    largura, altura = tamanho
    cov = projecao.covariancias_ndc.copy()
    cov[:, 0, 0] += (1.1 / largura)**2
    cov[:, 1, 1] += (1.1 / altura)**2
    valores, vetores = np.linalg.eigh(cov)
    eixos = vetores * np.sqrt(np.maximum(valores, 1e-12))[:, None, :]
    neblina = np.clip((projecao.profundidades - 6) / 30, 0, 0.35)[:, None]
    cores = projecao.cores.copy()
    cores[:, :3] = cores[:, :3] * (1 - neblina) + np.array([0.16, 0.25, 0.29]) * neblina
    return np.column_stack([projecao.centros_ndc, eixos[:, :, 0],
                            eixos[:, :, 1], cores]).astype("f4")


class _CacheInstanciasGaussianas:
    """Cache CPU de geometria estática, independente de OpenGL.

    Terreno e focos têm centros/covariâncias fixos. Sua projeção, descarte,
    autovetores e neblina só mudam com câmera ou tamanho do painel. Apenas
    a fumaça é reprojetada a cada instante. A combinação final usa novamente
    profundidade e ID original para preservar a ordem global, inclusive em
    empates. Alterar câmera ou resolução invalida o cache automaticamente.
    """
    def __init__(self, centros, covariancias, cores, tipos):
        self.centros = centros
        self.covariancias = covariancias
        self.cores = cores
        self.tipos = tipos
        self._estaticos = np.flatnonzero(tipos != 1)
        self._fumaca = np.flatnonzero(tipos == 1)
        self._chave_camera = None
        self._chave_frame = None
        self.indices_ordenados = np.empty(0, dtype=np.intp)
        self.reprojecoes_estaticas = 0
        self.reprojecoes_dinamicas = 0

    def preparar(self, view, tamanho, tempo=0.0, incendio=True):
        tamanho = tuple(tamanho)
        chave_camera = (view.tobytes(), tamanho)
        # Sem incêndio não existe geometria animada; o tempo é irrelevante.
        chave_frame = (chave_camera, incendio, float(tempo) if incendio else None)
        if chave_frame == self._chave_frame:
            return self._instancias
        aspecto = tamanho[0] / tamanho[1]
        if chave_camera != self._chave_camera:
            ids = self._estaticos
            projecao = projetar_gaussianas(
                self.centros[ids], self.covariancias[ids], self.cores[ids],
                view, aspecto=aspecto, near=0.2, far=80.0,
            )
            self._ids_estaticos = ids[projecao.indices]
            self._profundidades_estaticas = projecao.profundidades
            self._instancias_estaticas = _empacotar_instancias(projecao, tamanho)
            terreno = self.tipos[self._ids_estaticos] == 0
            self._ids_terreno = self._ids_estaticos[terreno]
            self._instancias_terreno = self._instancias_estaticas[terreno]
            self._linhas_fogo = np.flatnonzero(self.tipos[self._ids_estaticos] == 2)
            self._chave_camera = chave_camera
            self.reprojecoes_estaticas += 1

        if not incendio:
            self._instancias = self._instancias_terreno
            self.indices_ordenados = self._ids_terreno
        else:
            estaticas = self._instancias_estaticas.copy()
            linhas = self._linhas_fogo
            ids_fogo = self._ids_estaticos[linhas]
            estaticas[linhas, 9] = np.clip(
                self.cores[ids_fogo, 3] * (0.88 + 0.12 * np.sin(
                    tempo * 4.0 + self.centros[ids_fogo, 0] * 12)), 0, 1,
            )
            ids = self._fumaca
            centros = self.centros[ids].copy()
            centros[:, 0] += 0.10 * np.sin(tempo * 0.4 + self.centros[ids, 1])
            centros[:, 2] += 0.06 * np.sin(tempo * 0.28 + self.centros[ids, 1])
            projecao = projetar_gaussianas(
                centros, self.covariancias[ids], self.cores[ids], view,
                aspecto=aspecto, near=0.2, far=80.0,
            )
            dinamicas = _empacotar_instancias(projecao, tamanho)
            indices = np.concatenate([self._ids_estaticos, ids[projecao.indices]])
            profundidades = np.concatenate([self._profundidades_estaticas, projecao.profundidades])
            # O ID desempata do mesmo modo que argsort estável na cena integral.
            ordem = np.lexsort((indices, -profundidades))
            self._instancias = np.concatenate([estaticas, dinamicas])[ordem]
            self.indices_ordenados = indices[ordem]
            self.reprojecoes_dinamicas += 1
        self._chave_frame = chave_frame
        return self._instancias


VERTEX_SHADER = """
#version 330 core
in vec2 in_canto;
in vec2 in_centro;
in vec2 in_eixo_a;
in vec2 in_eixo_b;
in vec4 in_cor;
out vec2 v_local;
out vec4 v_cor;
void main() {
    v_local = in_canto;
    v_cor = in_cor;
    gl_Position = vec4(in_centro + in_eixo_a * in_canto.x + in_eixo_b * in_canto.y, 0.0, 1.0);
}
"""

FRAGMENT_SHADER = """
#version 330 core
in vec2 v_local;
in vec4 v_cor;
out vec4 fragColor;
void main() {
    float r2 = dot(v_local, v_local);
    if (r2 > 9.0) discard;
    float alpha = v_cor.a * exp(-0.5 * r2);
    if (alpha < 0.0039215686) discard;
    fragColor = vec4(v_cor.rgb * alpha, alpha);
}
"""

BACKGROUND_VERTEX = """
#version 330 core
in vec2 in_canto;
out vec2 v_uv;
void main() {
    gl_Position = vec4(in_canto / 3.0, 0.0, 1.0);
    v_uv = in_canto / 6.0 + 0.5;
}
"""

BACKGROUND_FRAGMENT = """
#version 330 core
in vec2 v_uv;
out vec4 fragColor;
void main() {
    vec3 cor = mix(vec3(0.11, 0.19, 0.23), vec3(0.025, 0.060, 0.105), v_uv.y);
    cor += vec3(0.15, 0.13, 0.075) * exp(-12.0 * distance(v_uv, vec2(0.18, 0.82)));
    cor *= 0.85 + 0.15 * (1.0 - dot(v_uv - 0.5, v_uv - 0.5));
    fragColor = vec4(cor, 1.0);
}
"""


class CenaGaussianas:
    """Cena GPU com recursos persistentes e câmera orbital em graus.

    ``renderizar(dados, viewport)`` desenha só no retângulo em pixels, com
    origem inferior esquerda, e restaura viewport e scissor do chamador.
    O aplicativo compartilha a convenção de alpha pré-multiplicado.
    """
    def __init__(self, ctx, quantidade=6000, seed=42):
        import moderngl
        self.ctx = ctx
        self.quantidade = int(quantidade)
        self.seed = seed
        self.centros, self.covariancias, self.cores, self.tipos = gerar_cena_sintetica(quantidade, seed)
        self._cache = _CacheInstanciasGaussianas(self.centros, self.covariancias, self.cores, self.tipos)
        self._chave_camera = None
        self._ultimas_instancias = None
        self.quantidade_visivel = 0
        self.tempo_projecao_ms = 0.0
        self._liberado = False
        self.reiniciar_camera()
        self.programa = ctx.program(vertex_shader=VERTEX_SHADER, fragment_shader=FRAGMENT_SHADER)
        self.programa_fundo = ctx.program(vertex_shader=BACKGROUND_VERTEX, fragment_shader=BACKGROUND_FRAGMENT)
        cantos = np.array([[-3, -3], [3, -3], [3, 3], [-3, -3], [3, 3], [-3, 3]], dtype="f4")
        self.quad = ctx.buffer(cantos.tobytes())
        self.instancias = ctx.buffer(reserve=max(40, self.quantidade * 40), dynamic=True)
        self.vao = ctx.vertex_array(self.programa, [
            (self.quad, "2f", "in_canto"),
            (self.instancias, "2f 2f 2f 4f /i", "in_centro", "in_eixo_a", "in_eixo_b", "in_cor"),
        ])
        self.vao_fundo = ctx.vertex_array(self.programa_fundo, [(self.quad, "2f", "in_canto")])
        self._modo_triangulos = moderngl.TRIANGLES

    def reiniciar_camera(self):
        self.azimute = 32.0
        self.elevacao = 38.0
        self.distancia = 12.0

    def renderizar(self, dados=None, viewport=None):
        import moderngl
        if self._liberado:
            return
        dados = dados or {}
        viewport = tuple(self.ctx.viewport if viewport is None else (int(v) for v in viewport))
        if len(viewport) != 4 or viewport[2] <= 0 or viewport[3] <= 0:
            return
        inicio = time.perf_counter()
        az = math.radians(float(self.azimute))
        el = math.radians(max(8.0, min(85.0, float(self.elevacao))))
        distancia = max(3.0, min(40.0, float(self.distancia)))
        chave_camera = (az, el, distancia)
        if chave_camera != self._chave_camera:
            alvo = np.array([0.0, 0.5, 0.0])
            pos = alvo + distancia * np.array([math.sin(az) * math.cos(el), math.sin(el), math.cos(az) * math.cos(el)])
            self._view = matriz_camera(pos, alvo)
            self._chave_camera = chave_camera
        instancias = self._cache.preparar(
            self._view, viewport[2:], tempo=float(dados.get("tempo", 0.0)),
            incendio=dados.get("cenario", "incendio") == "incendio",
        )
        self.quantidade_visivel = len(instancias)
        if len(instancias) and instancias is not self._ultimas_instancias:
            self.instancias.write(instancias.tobytes())
            self._ultimas_instancias = instancias
        self.tempo_projecao_ms = (time.perf_counter() - inicio) * 1000
        viewport_anterior = self.ctx.viewport
        # Scope restaura os estados de depth/cull/blend. O FBO atual precisa
        # ser preservado, pois a mesma cena serve às duas estratégias.
        escopo = self.ctx.scope(framebuffer=self.ctx.fbo, enable_only=moderngl.BLEND)
        try:
            with escopo:
                self.ctx.viewport = viewport
                # O clipping do próprio viewport limita todos os quads ao
                # painel. Não modificar scissor também preserva seu estado
                # habilitado/desabilitado (o getter ModernGL só expõe a caixa).
                self.ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
                self.vao_fundo.render(mode=self._modo_triangulos)
                if self.quantidade_visivel:
                    self.vao.render(mode=self._modo_triangulos, instances=self.quantidade_visivel)
        finally:
            escopo.release()
            self.ctx.viewport = viewport_anterior
            self.ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA

    def release(self):
        """Libera os recursos OpenGL; chamadas repetidas são seguras."""
        if self._liberado:
            return
        self._liberado = True
        for recurso in (self.vao, self.vao_fundo, self.instancias, self.quad,
                        self.programa, self.programa_fundo):
            recurso.release()
