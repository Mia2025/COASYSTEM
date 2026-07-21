"""
Gera fixtures/budget_sample.pdf — orçamento fictício de condomínio para testar
o fluxo de análise. Inclui um erro proposital de soma (a seção de despesas soma
$1.237.000 mas o total impresso é $1.242.000) para exercitar a validação V1.
Só stdlib — PDF construído à mão.
"""
import os

LINES = [
    "SEASIDE TOWERS CONDOMINIUM ASSOCIATION, INC.",
    "PROPOSED ANNUAL BUDGET - FISCAL YEAR 2027 (DRAFT)",
    "100 Units - Miami Beach, Florida",
    "",
    "REVENUE                              2026        2027",
    "Maintenance Assessments         1,020,000   1,224,000",
    "Late Fees                           6,000       6,000",
    "Prior Year Surplus                      0      12,000",
    "TOTAL REVENUE                   1,026,000   1,242,000",
    "",
    "OPERATING EXPENSES                   2026        2027",
    "Insurance                         430,000     612,000",
    "Payroll & Benefits                228,000     240,000",
    "Utilities                         120,000     126,000",
    "Elevator Maintenance Contract      48,000      24,000",
    "Elevator Repairs                   10,000      35,000",
    "Landscaping                        36,000      38,000",
    "Management Fee                     60,000      66,000",
    "Miscellaneous                      24,000      96,000",
    "TOTAL OPERATING EXPENSES          956,000   1,242,000",
    "",
    "RESERVES",
    "Roof (replacement 2031, cost 400,000, balance 90,000)   annual 20,000",
    "Painting (2029, cost 180,000, balance 60,000)           annual 15,000",
    "",
    "Note from the Board: We are pleased to report NO INCREASE",
    "in your monthly assessment this year.",
    "Monthly assessment per unit: 2026: $850   2027: $1,020",
]


def esc(s):
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build():
    content = ["BT /F1 10 Tf 40 760 Td 14 TL"]
    for i, ln in enumerate(LINES):
        if i:
            content.append("T*")
        content.append(f"({esc(ln)}) Tj")
    content.append("ET")
    stream = "\n".join(content).encode("latin-1")

    objs = []
    objs.append(b"<< /Type /Catalog /Pages 2 0 R >>")
    objs.append(b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>")
    objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>")
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>")
    objs.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream")

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objs)+1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs)+1} /Root 1 0 R >>\n"
            f"startxref\n{xref_at}\n%%EOF\n").encode()
    return bytes(out)


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, "fixtures", "budget_sample.pdf")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "wb").write(build())
    print("ok ->", path, os.path.getsize(path), "bytes")
