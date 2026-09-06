/* Marca da Tractian como SVG inline.
 *
 * Desenhada em vetor, e nao embutida como PNG: o arquivo do logotipo vem com fundo
 * branco solido, que num tema escuro vira um retangulo aceso no canto da pagina. Em SVG
 * o fundo nao existe e o traco herda `currentColor` — no tema Tractian assume o azul da
 * marca, nos demais acompanha a tinta da pagina.
 *
 * O traco que define o logotipo e o CORTE DIAGONAL, sempre no mesmo angulo e sempre
 * descendo da esquerda para a direita: o T tem a serifa cortada, o R e o A trazem a
 * perna inclinada, o C abre em bisel em vez de curva, e o N fecha a palavra com a
 * diagonal mais longa. Todas as formas abaixo sao poligonos retos — nenhuma curva —
 * porque e assim que a marca e construida.
 *
 * Reconstrucao para uso interno na demonstracao; nao e o arquivo oficial da marca.
 */

/* Geometria: caixa alta de 120 unidades numa viewBox de altura 150.
   O corte diagonal usa deslocamento horizontal de 26 sobre 120 de altura. */
const LETRAS = `
  <!-- T: haste central, com o canto inferior direito da barra cortado em diagonal -->
  <path d="M0 8h150l-8 26H93v112H59V34H0z"/>

  <!-- R: ombro reto, vinco diagonal e perna que sai inclinada -->
  <path d="M170 8h88c30 0 50 18 50 46 0 20-11 35-29 42l36 50h-40l-32-45h-39v45h-34zm34 26v38h52c13 0 21-7 21-19s-8-19-21-19z"/>

  <!-- A: haste esquerda vertical, haste direita inclinada, vertice chanfrado -->
  <path d="M370 8h40l60 138h-36l-11-27h-66l-11 27h-36zm19 33-21 52h42z"/>

  <!-- C: bisel no canto superior e inferior, sem curva -->
  <path d="M560 6c30 0 54 13 66 34l-27 15c-8-13-22-21-39-21-26 0-44 17-44 43s18 43 44 43c17 0 31-8 39-21l27 15c-12 21-36 34-66 34-45 0-76-29-76-71s31-71 76-71z"/>

  <!-- T menor, mesmo corte -->
  <path d="M646 8h140l-8 26h-49v112h-34V34h-49z"/>

  <!-- I -->
  <path d="M800 8h34v138h-34z"/>

  <!-- A -->
  <path d="M862 8h40l60 138h-36l-11-27h-66l-11 27h-36zm19 33-21 52h42z"/>

  <!-- N: diagonal longa ligando as duas hastes, o fecho da palavra -->
  <path d="M978 8h34l62 88V8h34v138h-34l-62-88v88h-34z"/>
`;

export function marcaTractian(altura = 15) {
  const larg = Math.round((altura * 1108) / 154);
  return `<svg class="marca" width="${larg}" height="${altura}" viewBox="0 0 1108 154"
    role="img" aria-label="Tractian" fill="currentColor" focusable="false">${LETRAS}</svg>`;
}
