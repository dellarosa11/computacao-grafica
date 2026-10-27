"""
compositor.py - Camada de Composição Gráfica (Composition Layer)
Implementa tanto a arquitetura multicamada (composição via Framebuffer Objects - FBOs)
quanto o modo monolítico de passagem única para comparação experimental (Seção III.B/D).
"""

import numpy as np
import moderngl
from renderizador import configurar_blending

VERTEX_SHADER_COMPOSITE = """
#version 330 core
in vec2 in_pos;
in vec2 in_uv;

out vec2 v_uv;

void main() {
    v_uv = in_uv;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

FRAGMENT_SHADER_COMPOSITE = """
#version 330 core
uniform sampler2D u_layer_tex;
uniform float u_opacity;

in vec2 v_uv;
out vec4 fragColor;

void main() {
    vec4 tex = texture(u_layer_tex, v_uv);
    // As texturas já contêm RGB pré-multiplicado: opacidade escala RGBA.
    fragColor = tex * u_opacity;
}
"""


class CompositorMulticamada:
    """Gerenciador de FBOs, texturas de camada e shader de composição gráfica."""
    def __init__(self, ctx: moderngl.Context, largura: int, altura: int, num_camadas: int = 4):
        self.ctx = ctx
        self._validar_dimensoes(largura, altura)
        self._validar_camadas(num_camadas)
        self.largura = int(largura)
        self.altura = int(altura)
        self.num_camadas = int(num_camadas)
        self._released = False
        
        # Shader para o passe de composição em tela cheia
        self.prog_composite = ctx.program(
            vertex_shader=VERTEX_SHADER_COMPOSITE,
            fragment_shader=FRAGMENT_SHADER_COMPOSITE,
        )
        
        # Quad de tela cheia (-1 a 1) com UVs (0 a 1)
        quad_verts = np.array([
            # pos(x,y), uv(u,v)
            -1.0, -1.0,  0.0, 0.0,
             1.0, -1.0,  1.0, 0.0,
             1.0,  1.0,  1.0, 1.0,
            -1.0, -1.0,  0.0, 0.0,
             1.0,  1.0,  1.0, 1.0,
            -1.0,  1.0,  0.0, 1.0,
        ], dtype='f4')
        self.quad_vbo = ctx.buffer(quad_verts.tobytes())
        self.quad_vao = ctx.vertex_array(
            self.prog_composite,
            [(self.quad_vbo, '2f 2f', 'in_pos', 'in_uv')],
        )

        self.fbos = []
        self.texturas = []
        self.camadas_ativas = [True] * num_camadas
        self._alocar_fbos()

    @staticmethod
    def _validar_dimensoes(largura, altura):
        if int(largura) <= 0 or int(altura) <= 0:
            raise ValueError('As dimensões dos buffers devem ser positivas.')

    @staticmethod
    def _validar_camadas(numero):
        if int(numero) not in (2, 4):
            raise ValueError('Use 2 ou 4 camadas para a interface aeronáutica.')

    def _alocar_fbos(self):
        if self._released:
            raise RuntimeError('O compositor já foi liberado.')
        # Aloca antes de liberar o conjunto anterior; uma falha não deixa meias camadas.
        novas_texturas, novos_fbos = [], []
        try:
            for _ in range(self.num_camadas):
                tex = self.ctx.texture((self.largura, self.altura), 4, dtype='f1')
                novas_texturas.append(tex)
                tex.filter = (moderngl.NEAREST, moderngl.NEAREST)
                tex.repeat_x = tex.repeat_y = False
                novos_fbos.append(self.ctx.framebuffer(color_attachments=[tex]))
        except Exception:
            for recurso in novos_fbos + novas_texturas:
                recurso.release()
            raise
        for recurso in self.fbos + self.texturas:
            recurso.release()
        self.texturas, self.fbos = novas_texturas, novos_fbos

    def redimensionar(self, nova_largura: int, nova_altura: int):
        """Redimensiona buffers ao alterar resolução."""
        self._validar_dimensoes(nova_largura, nova_altura)
        if self.largura == nova_largura and self.altura == nova_altura:
            return
        anterior = self.largura, self.altura
        self.largura, self.altura = int(nova_largura), int(nova_altura)
        try:
            self._alocar_fbos()
        except Exception:
            self.largura, self.altura = anterior
            raise

    def definir_num_camadas(self, novo_num: int):
        """Alterna dinamicamente entre 2 ou 4 camadas."""
        self._validar_camadas(novo_num)
        if self.num_camadas == novo_num:
            return
        anterior = self.num_camadas
        self.num_camadas = int(novo_num)
        try:
            self._alocar_fbos()
        except Exception:
            self.num_camadas = anterior
            raise
        self.camadas_ativas = [True] * self.num_camadas

    def limpar_camadas(self):
        """Passo 1 do Algoritmo de Composição: limpa os buffers intermediários."""
        for fbo in self.fbos:
            fbo.clear(0.0, 0.0, 0.0, 0.0)

    def obter_fbo(self, indice_camada: int) -> moderngl.Framebuffer:
        return self.fbos[indice_camada]

    def compor(self, fbo_destino=None, cor_fundo=(0.02, 0.03, 0.07, 1.0)):
        """
        Passos 5 e 6 do Algoritmo de Composição (Seção III.D):
        Aplica a composição das camadas segundo a ordem definida sobre o framebuffer final.
        """
        if fbo_destino is None:
            fbo_destino = self.ctx.screen
            
        fbo_destino.use()
        self.ctx.viewport = (0, 0, self.largura, self.altura)
        
        # Limpa o framebuffer de destino com cor de fundo aero
        r, g, b, a = cor_fundo
        fbo_destino.clear(r * a, g * a, b * a, a)
        
        # Habilita blending para sobreposição correta das camadas transparentes
        configurar_blending(self.ctx)
        
        self.prog_composite['u_opacity'].value = 1.0
        
        # Composição sequencial (Camada 0 até N-1)
        for i in range(self.num_camadas):
            if not self.camadas_ativas[i]:
                continue
            self.texturas[i].use(location=0)
            self.prog_composite['u_layer_tex'].value = 0
            self.quad_vao.render(moderngl.TRIANGLES, vertices=6)

    def release(self):
        """Libera recursos explicitamente; chamadas repetidas são seguras."""
        if self._released:
            return
        self._released = True
        for recurso in self.fbos + self.texturas:
            recurso.release()
        self.fbos.clear()
        self.texturas.clear()
        for recurso in (self.quad_vao, self.quad_vbo, self.prog_composite):
            recurso.release()
