#!/usr/bin/env python3
"""
Relatorio de Cambio - gerador.
Le o texto do boletim (corpo da issue), pede ao Claude apenas os campos de
cambio em JSON e encaixa no template modelo-cambio.html.
"""
import os
import sys
import json
import re
from anthropic import Anthropic

MODELO = "modelo-cambio.html"
SAIDA = "index.html"

# Bandeiras desenhadas em SVG: nao dependem de fonte nem de emoji.
BANDEIRAS = {
    "BR": '<svg viewBox="0 0 28 20"><rect width="28" height="20" fill="#009B3A"/>'
          '<path d="M14 2.5 25.5 10 14 17.5 2.5 10Z" fill="#FEDF00"/>'
          '<circle cx="14" cy="10" r="4.2" fill="#002776"/></svg>',
    "US": '<svg viewBox="0 0 28 20"><rect width="28" height="20" fill="#fff"/>'
          '<g fill="#B22234"><rect width="28" height="1.55" y="0"/>'
          '<rect width="28" height="1.55" y="3.1"/><rect width="28" height="1.55" y="6.2"/>'
          '<rect width="28" height="1.55" y="9.3"/><rect width="28" height="1.55" y="12.4"/>'
          '<rect width="28" height="1.55" y="15.5"/><rect width="28" height="1.55" y="18.4"/></g>'
          '<rect width="12" height="10.8" fill="#3C3B6E"/></svg>',
    "EU": '<svg viewBox="0 0 28 20"><rect width="28" height="20" fill="#003399"/>'
          '<g fill="#FFCC00"><circle cx="14" cy="5" r="1"/><circle cx="17.5" cy="6" r="1"/>'
          '<circle cx="19.5" cy="9" r="1"/><circle cx="18.5" cy="12.5" r="1"/>'
          '<circle cx="14" cy="14" r="1"/><circle cx="9.5" cy="12.5" r="1"/>'
          '<circle cx="8.5" cy="9" r="1"/><circle cx="10.5" cy="6" r="1"/></g></svg>',
    "GB": '<svg viewBox="0 0 28 20"><rect width="28" height="20" fill="#012169"/>'
          '<path d="M0 0 28 20M28 0 0 20" stroke="#fff" stroke-width="4"/>'
          '<path d="M0 0 28 20M28 0 0 20" stroke="#C8102E" stroke-width="2"/>'
          '<path d="M14 0v20M0 10h28" stroke="#fff" stroke-width="6"/>'
          '<path d="M14 0v20M0 10h28" stroke="#C8102E" stroke-width="3.5"/></svg>',
    "JP": '<svg viewBox="0 0 28 20"><rect width="28" height="20" fill="#fff"/>'
          '<circle cx="14" cy="10" r="5.5" fill="#BC002D"/></svg>',
    "CN": '<svg viewBox="0 0 28 20"><rect width="28" height="20" fill="#DE2910"/>'
          '<g fill="#FFDE00"><circle cx="6" cy="5.5" r="2.6"/><circle cx="11.5" cy="2.6" r="0.9"/>'
          '<circle cx="13.6" cy="5" r="0.9"/><circle cx="13.2" cy="8.2" r="0.9"/>'
          '<circle cx="10.8" cy="10" r="0.9"/></g></svg>',
    "DE": '<svg viewBox="0 0 28 20"><rect width="28" height="6.7" fill="#000"/>'
          '<rect width="28" height="6.7" y="6.7" fill="#DD0000"/>'
          '<rect width="28" height="6.6" y="13.4" fill="#FFCE00"/></svg>',
    "MX": '<svg viewBox="0 0 28 20"><rect width="9.4" height="20" fill="#006847"/>'
          '<rect width="9.2" height="20" x="9.4" fill="#fff"/>'
          '<rect width="9.4" height="20" x="18.6" fill="#CE1126"/></svg>',
    "AR": '<svg viewBox="0 0 28 20"><rect width="28" height="20" fill="#fff"/>'
          '<rect width="28" height="6.7" fill="#74ACDF"/>'
          '<rect width="28" height="6.7" y="13.3" fill="#74ACDF"/>'
          '<circle cx="14" cy="10" r="2.2" fill="#F6B40E"/></svg>',
    "XX": '<svg viewBox="0 0 28 20"><rect width="28" height="20" fill="#C9C4B8"/></svg>',
}


def bandeira_svg(codigo):
    return BANDEIRAS.get((codigo or "XX").upper(), BANDEIRAS["XX"])


def dados_da_issue():
    titulo = os.getenv("ISSUE_TITLE", "").strip()
    corpo = os.getenv("ISSUE_BODY", "").strip()
    if not corpo:
        print("ERRO: corpo da issue vazio")
        sys.exit(1)
    return titulo, corpo


def carregar_modelo():
    if not os.path.exists(MODELO):
        print(f"ERRO: {MODELO} nao encontrado na raiz do repositorio")
        sys.exit(1)
    with open(MODELO, encoding="utf-8") as f:
        return f.read()


PROMPT = """Voce recebe o texto bruto de um boletim de mercado brasileiro.
Monte a partir dele um RELATORIO DE CAMBIO: aproveite apenas o que for de
cambio (dolar, moedas, fluxo, Banco Central) e a agenda do dia. Ignore bolsa,
eleicoes, Petrobras e noticias de juros que nao tenham efeito sobre a moeda.

Devolva APENAS um objeto JSON valido: sem markdown, sem crases, sem nenhum
texto antes ou depois.

Chaves obrigatorias:
- DATA_LONGA: data por extenso, ex "Sexta-feira, 18 de setembro de 2026"
- DATA_CURTA: ex "18/09/2026"
- DESCRIPTION: manchete resumida em uma linha, ate 150 caracteres. Esta linha
  vira a descricao do card no Teams: comece pelo dolar e pela variacao do dia.
- MANCHETE_TITULO: titulo curto da manchete, em MAIUSCULAS
- MANCHETE_TEXTO: paragrafo de abertura sobre o cambio, 2 a 4 frases

PAINEL 1:
- DOLAR, DXY, CDS_BR, BRENT: valores de fechamento (ex "5,1543", "98,42",
  "120 pb", "US$ 67,30")
- DOLAR_VAR, DXY_VAR, CDS_BR_VAR, BRENT_VAR: variacao, ex "+0,14%" ou "—"
- DOLAR_COR, DXY_COR, CDS_BR_COR, BRENT_COR: "pos" se subiu, "neg" se caiu,
  "neu" se estavel ou sem dado

PAINEL 2:
- PTAX, EURUSD, USDCNH, TNOTE: valores (ex "5,1489", "1,1742", "7,1085",
  "4,18%")
- PTAX_VAR, EURUSD_VAR, USDCNH_VAR, TNOTE_VAR: variacao
- PTAX_COR, EURUSD_COR, USDCNH_COR, TNOTE_COR: "pos", "neg" ou "neu"

- AGENDA: lista de objetos com as chaves "pais" (codigo de duas letras do pais:
  BR, US, EU, GB, JP, CN, DE, MX, AR; use XX se nao se aplicar),
  "hora" (ex "8h00" ou "no dia"), "titulo" e "detalhe" (detalhe pode ser "").
  Mantenha a agenda inteira do boletim, nao apenas os eventos de cambio.

- TEXTO_DOLAR: como o dolar se comportou no dia e por que.
- TEXTO_EXTERIOR: DXY, moedas de emergentes e pares relevantes.
- TEXTO_FLUXO_BC: fluxo cambial, leiloes, swap e atuacao do Banco Central.

Regras:
- Nao invente numeros que nao estao no texto; preserve os valores exatamente
  como aparecem no boletim.
- Se nao houver informacao sobre algum indicador, use "—" como valor e "neu"
  como cor.
- Se nao houver informacao para uma secao, use "Nenhuma noticia relevante."
- Nao use markdown dentro dos textos (nada de ** ou #).
- Nos textos das secoes, envolva cada numero em <span class="num">...</span>.

TEXTO DO BOLETIM:
---
{corpo}
---"""


def pedir_campos(corpo):
    client = Anthropic()
    resp = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        messages=[{"role": "user", "content": PROMPT.format(corpo=corpo)}],
    )
    bruto = "".join(b.text for b in resp.content if b.type == "text").strip()
    bruto = re.sub(r"^```(?:json)?|```$", "", bruto, flags=re.MULTILINE).strip()
    try:
        return json.loads(bruto)
    except json.JSONDecodeError as e:
        print(f"ERRO ao interpretar o JSON devolvido pelo Claude: {e}")
        print("--- inicio da resposta ---")
        print(bruto[:800])
        sys.exit(1)


def montar_agenda(itens):
    linhas = []
    for it in itens or []:
        detalhe = (it.get("detalhe") or "").strip()
        bloco = f"\n          <span>{detalhe}</span>" if detalhe else ""
        linhas.append(
            "      <li>\n"
            f'        <span class="bandeira">{bandeira_svg(it.get("pais"))}</span>\n'
            f'        <span class="hora">{it.get("hora", "")}</span>\n'
            '        <span class="desc">\n'
            f'          <strong>{it.get("titulo", "")}</strong>{bloco}\n'
            "        </span>\n"
            "      </li>"
        )
    return "\n".join(linhas)


def preencher(modelo, campos):
    html = modelo

    agenda_html = montar_agenda(campos.get("AGENDA"))
    html = re.sub(
        r'(<ul class="agenda-lista">).*?(</ul>)',
        lambda m: m.group(1) + "\n" + agenda_html + "\n    " + m.group(2),
        html,
        flags=re.DOTALL,
    )

    campos.setdefault("DATA_CURTA_FOOTER", campos.get("DATA_CURTA", ""))

    for chave, valor in campos.items():
        if chave == "AGENDA":
            continue
        html = html.replace("{{" + chave + "}}", str(valor))

    html = re.sub(r"\{\{[A-Z_]+\}\}", "", html)
    return html


def main():
    print("Iniciando geracao do Relatorio de Cambio...")
    titulo, corpo = dados_da_issue()
    print(f"Titulo: {titulo}")
    print(f"Corpo: {len(corpo)} caracteres")

    modelo = carregar_modelo()
    print("Modelo carregado.")

    campos = pedir_campos(corpo)
    print(f"Campos recebidos: {len(campos)}")

    html = preencher(modelo, campos)

    with open(SAIDA, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"{SAIDA} salvo ({len(html)} bytes)")
    print("Relatorio gerado com sucesso.")


if __name__ == "__main__":
    main()
