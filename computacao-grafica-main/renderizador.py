"""Primitivas e texto OpenGL com buffers dinâmicos e alfa pré-multiplicado.

As cores recebidas pela API são RGBA convencional; os shaders convertem a
saída para alfa pré-multiplicado, inclusive a cobertura antialias dos glifos.
"""

import math
import unicodedata

import moderngl
import numpy as np
from PIL import Image, ImageDraw, ImageFont


VERTEX_SHADER_PRIMITIVES = """
#version 330 core
in vec2 in_pos;
in vec4 in_color;
out vec4 v_color;
void main() {
    v_color = in_color;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

FRAGMENT_SHADER_PRIMITIVES = """
#version 330 core
in vec4 v_color;
out vec4 fragColor;
void main() {
    fragColor = vec4(v_color.rgb * v_color.a, v_color.a);
}
"""

VERTEX_SHADER_TEXTURE = """
#version 330 core
in vec2 in_pos;
in vec2 in_uv;
in vec4 in_color;
out vec2 v_uv;
out vec4 v_color;
void main() {
    v_uv = in_uv;
    v_color = in_color;
    gl_Position = vec4(in_pos, 0.0, 1.0);
}
"""

FRAGMENT_SHADER_TEXTURE = """
#version 330 core
uniform sampler2D u_texture;
in vec2 v_uv;
in vec4 v_color;
out vec4 fragColor;
void main() {
    float alpha = texture(u_texture, v_uv).a * v_color.a;
    fragColor = vec4(v_color.rgb * alpha, alpha);
}
"""

# Mantidos para compatibilidade com clientes que importavam estes shaders.
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
    fragColor = texture(u_layer_tex, v_uv) * u_opacity;
}
"""


def configurar_blending(ctx):
    """Contrato de todos os passes: RGB e alfa já pré-multiplicados."""
    ctx.enable(moderngl.BLEND)
    ctx.blend_func = moderngl.ONE, moderngl.ONE_MINUS_SRC_ALPHA
    ctx.blend_equation = moderngl.FUNC_ADD


class PrimitiveBatch:
    """Lote de triângulos que cresce sem descartar geometrias silenciosamente."""

    def __init__(self, ctx: moderngl.Context, max_vertices=65536):
        self.ctx = ctx
        self.max_vertices = max(6, int(max_vertices))
        self.vertex_size = 6 * 4
        self._released = False
        self.prog = ctx.program(vertex_shader=VERTEX_SHADER_PRIMITIVES,
                                fragment_shader=FRAGMENT_SHADER_PRIMITIVES)
        self.vbo = ctx.buffer(reserve=self.max_vertices * self.vertex_size, dynamic=True)
        self.vao = ctx.vertex_array(self.prog, [(self.vbo, '2f 4f', 'in_pos', 'in_color')])
        self.buffer = np.empty(self.max_vertices * 6, dtype='f4')
        self.vertex_count = 0

    def _reservar(self, total):
        if self._released:
            raise RuntimeError('O lote de primitivas já foi liberado.')
        if total <= self.max_vertices:
            return
        nova_capacidade = max(total, self.max_vertices * 2)
        novo_buffer = np.empty(nova_capacidade * 6, dtype='f4')
        novo_buffer[:self.vertex_count * 6] = self.buffer[:self.vertex_count * 6]
        self.vbo.orphan(nova_capacidade * self.vertex_size)
        self.buffer = novo_buffer
        self.max_vertices = nova_capacidade

    def limpar(self):
        self.vertex_count = 0

    def adicionar_triangulos_numpy(self, arr: np.ndarray):
        """Adiciona vértices [x,y,r,g,b,a]; aceita arrays planos ou matriciais."""
        arr = np.asarray(arr, dtype='f4').reshape(-1)
        if arr.size % 18:
            raise ValueError('O lote deve conter triângulos completos de 3 vértices RGBA.')
        qtd = arr.size // 6
        if not qtd:
            return
        self._reservar(self.vertex_count + qtd)
        inicio = self.vertex_count * 6
        self.buffer[inicio:inicio + arr.size] = arr
        self.vertex_count += qtd

    def adicionar_retangulo(self, x, y, w, h, r, g, b, a=1.0):
        self._reservar(self.vertex_count + 6)
        x2, y2 = x + w, y + h
        dados = [x, y, r, g, b, a, x2, y, r, g, b, a, x2, y2, r, g, b, a,
                 x, y, r, g, b, a, x2, y2, r, g, b, a, x, y2, r, g, b, a]
        inicio = self.vertex_count * 6
        self.buffer[inicio:inicio + 36] = dados
        self.vertex_count += 6

    def adicionar_retangulo_rotacionado(self, cx, cy, w, h, angulo_rad, r, g, b, a=1.0):
        self._reservar(self.vertex_count + 6)
        cos_a, sin_a = math.cos(angulo_rad), math.sin(angulo_rad)
        pontos = [(cx + x * cos_a - y * sin_a, cy + x * sin_a + y * cos_a)
                  for x, y in [(-w/2, -h/2), (w/2, -h/2), (w/2, h/2), (-w/2, h/2)]]
        inicio = self.vertex_count * 6
        self.buffer[inicio:inicio + 36] = [v for i in (0, 1, 2, 0, 2, 3)
                                         for v in (*pontos[i], r, g, b, a)]
        self.vertex_count += 6

    def adicionar_linha(self, x1, y1, x2, y2, espessura, r, g, b, a=1.0):
        dx, dy = x2 - x1, y2 - y1
        comprimento = math.hypot(dx, dy)
        if comprimento < 1e-8 or espessura <= 0:
            return
        self.adicionar_retangulo_rotacionado((x1+x2)/2, (y1+y2)/2, comprimento,
                                             espessura, math.atan2(dy, dx), r, g, b, a)

    def adicionar_circulo(self, cx, cy, raio_x, raio_y, num_segmentos, r, g, b,
                         a=1.0, preenchido=False, espessura=0.003):
        num_segmentos = max(3, int(num_segmentos))
        passo = math.tau / num_segmentos
        if preenchido:
            self._reservar(self.vertex_count + num_segmentos * 3)
            for i in range(num_segmentos):
                a1, a2 = i * passo, (i + 1) * passo
                inicio = self.vertex_count * 6
                self.buffer[inicio:inicio + 18] = [
                    cx, cy, r, g, b, a,
                    cx+raio_x*math.cos(a1), cy+raio_y*math.sin(a1), r, g, b, a,
                    cx+raio_x*math.cos(a2), cy+raio_y*math.sin(a2), r, g, b, a]
                self.vertex_count += 3
        else:
            for i in range(num_segmentos):
                a1, a2 = i * passo, (i + 1) * passo
                self.adicionar_linha(cx+raio_x*math.cos(a1), cy+raio_y*math.sin(a1),
                                     cx+raio_x*math.cos(a2), cy+raio_y*math.sin(a2),
                                     espessura, r, g, b, a)

    def renderizar(self):
        if self._released:
            raise RuntimeError('O lote de primitivas já foi liberado.')
        if not self.vertex_count:
            return
        configurar_blending(self.ctx)
        self.vbo.write(self.buffer[:self.vertex_count * 6].tobytes())
        self.vao.render(moderngl.TRIANGLES, vertices=self.vertex_count)

    def release(self):
        if self._released:
            return
        self._released = True
        self.vao.release()
        self.vbo.release()
        self.prog.release()
        self.buffer = np.empty(0, dtype='f4')
        self.vertex_count = 0


class FontAtlasRenderer:
    """Texto com métricas reais, acentos portugueses e atlas sem vazamento entre glifos."""

    def __init__(self, ctx: moderngl.Context, max_chars=4000):
        self.ctx = ctx
        self.max_chars = max(1, int(max_chars))
        self.vertex_size = 8 * 4
        self.vertex_count = 0
        self._released = False
        self._aspecto = 1.0
        self.prog = ctx.program(vertex_shader=VERTEX_SHADER_TEXTURE,
                                fragment_shader=FRAGMENT_SHADER_TEXTURE)
        self.vbo = ctx.buffer(reserve=self.max_chars * 6 * self.vertex_size, dynamic=True)
        self.vao = ctx.vertex_array(self.prog, [(self.vbo, '2f 2f 4f', 'in_pos', 'in_uv', 'in_color')])
        self.buffer = np.empty(self.max_chars * 6 * 8, dtype='f4')
        self._criar_atlas()

    def _criar_atlas(self):
        candidatos = ['C:/Windows/Fonts/segoeui.ttf', 'C:/Windows/Fonts/consola.ttf', 'C:/Windows/Fonts/arial.ttf',
                      '/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf',
                      '/System/Library/Fonts/Menlo.ttc', 'DejaVuSansMono.ttf']
        for caminho in candidatos:
            try:
                fonte = ImageFont.truetype(caminho, 42)
                break
            except OSError:
                continue
        else:
            fonte = ImageFont.load_default(size=42)
        self.fonte_path = str(getattr(fonte, 'path', 'Pillow default'))
        self.ascent, descent = fonte.getmetrics()
        self.line_height = self.ascent + descent
        caracteres = ''.join(chr(c) for c in range(32, 127))
        caracteres += ''.join(chr(c) for c in range(160, 256)) + '–—−→←↑↓✓•…ΩΔ'
        caracteres = ''.join(dict.fromkeys(caracteres))
        padding = 3
        caixas = {ch: fonte.getbbox(ch, anchor='ls') for ch in caracteres}
        cell_w = max(b[2] - b[0] for b in caixas.values()) + 2 * padding + 2
        cell_h = max(b[3] - b[1] for b in caixas.values()) + 2 * padding + 2
        cols = 16
        self.atlas_w = 2 ** math.ceil(math.log2(cols * cell_w))
        self.atlas_h = 2 ** math.ceil(math.log2(math.ceil(len(caracteres)/cols) * cell_h))
        imagem = Image.new('RGBA', (self.atlas_w, self.atlas_h), (255, 255, 255, 0))
        desenho = ImageDraw.Draw(imagem)
        self.char_uvs, self.char_metrics = {}, {}
        for indice, ch in enumerate(caracteres):
            left, top, right, bottom = caixas[ch]
            px, py = indice % cols * cell_w, indice // cols * cell_h
            largura, altura = right - left + 2*padding, bottom - top + 2*padding
            desenho.text((px+padding-left, py+padding-top), ch, font=fonte,
                         anchor='ls', fill=(255, 255, 255, 255))
            self.char_uvs[ch] = (px/self.atlas_w, py/self.atlas_h,
                                 (px+largura)/self.atlas_w, (py+altura)/self.atlas_h)
            self.char_metrics[ch] = (left-padding, top-padding, right+padding,
                                     bottom+padding, float(fonte.getlength(ch)))
        self.texture = self.ctx.texture((self.atlas_w, self.atlas_h), 4, imagem.tobytes())
        self.texture.filter = moderngl.LINEAR, moderngl.LINEAR
        self.texture.repeat_x = self.texture.repeat_y = False

    def set_viewport(self, largura, altura):
        if largura <= 0 or altura <= 0:
            raise ValueError('A largura e altura da área de desenho devem ser positivas.')
        self._aspecto = float(altura) / float(largura)

    def limpar(self):
        self.vertex_count = 0

    def _reservar(self, total_vertices):
        if self._released:
            raise RuntimeError('O atlas de fontes já foi liberado.')
        if total_vertices <= self.max_chars * 6:
            return
        capacidade = max(math.ceil(total_vertices/6), self.max_chars*2)
        novo = np.empty(capacidade * 6 * 8, dtype='f4')
        novo[:self.vertex_count*8] = self.buffer[:self.vertex_count*8]
        self.vbo.orphan(capacidade * 6 * self.vertex_size)
        self.buffer, self.max_chars = novo, capacidade

    def medir_texto(self, texto, tamanho=0.04):
        """Retorna largura e altura em NDC, respeitando tamanho, aspecto e novas linhas."""
        linhas = unicodedata.normalize('NFC', str(texto)).split('\n')
        larguras = [sum(self.char_metrics.get(ch, self.char_metrics['?'])[4]
                        for ch in linha.replace('\t', '    ')) for linha in linhas]
        return max(larguras, default=0)*tamanho/self.line_height*self._aspecto, len(linhas)*tamanho

    def desenhar_texto(self, texto: str, x: float, y: float, tamanho: float = 0.04,
                       r: float = 1.0, g: float = 1.0, b: float = 1.0, a: float = 1.0):
        """Desenha uma linha centrada em y; tamanho é a altura da linha em NDC."""
        if tamanho <= 0:
            return
        texto = unicodedata.normalize('NFC', str(texto)).replace('\t', '    ')
        self._reservar(self.vertex_count + len(texto)*6)
        sy = tamanho/self.line_height
        sx = sy*self._aspecto
        cur_x = x
        baseline = y + tamanho/2 - self.ascent*sy
        for ch in texto:
            if ch == '\n':
                cur_x = x
                baseline -= tamanho
                continue
            if ch not in self.char_metrics:
                ch = '?'
            left, top, right, bottom, avance = self.char_metrics[ch]
            if ch.isspace():
                cur_x += avance*sx
                continue
            x1, x2 = cur_x+left*sx, cur_x+right*sx
            y1, y2 = baseline-bottom*sy, baseline-top*sy
            u0, v0, u1, v1 = self.char_uvs[ch]
            inicio = self.vertex_count*8
            self.buffer[inicio:inicio+48] = [
                x1,y1,u0,v1,r,g,b,a, x2,y1,u1,v1,r,g,b,a, x2,y2,u1,v0,r,g,b,a,
                x1,y1,u0,v1,r,g,b,a, x2,y2,u1,v0,r,g,b,a, x1,y2,u0,v0,r,g,b,a]
            self.vertex_count += 6
            cur_x += avance*sx

    def renderizar(self):
        if self._released:
            raise RuntimeError('O atlas de fontes já foi liberado.')
        if not self.vertex_count:
            return
        configurar_blending(self.ctx)
        self.texture.use(location=0)
        self.prog['u_texture'].value = 0
        self.vbo.write(self.buffer[:self.vertex_count*8].tobytes())
        self.vao.render(moderngl.TRIANGLES, vertices=self.vertex_count)

    def release(self):
        if self._released:
            return
        self._released = True
        for recurso in (self.vao, self.vbo, self.texture, self.prog):
            recurso.release()
        self.buffer = np.empty(0, dtype='f4')
        self.vertex_count = 0
