import os
from fpdf import FPDF

out_dir = r"e:\Uber\routecraft\output"

images = {
    "home": os.path.join(out_dir, "routecraft_home.jpg"),
    "results": os.path.join(out_dir, "routecraft_results.jpg"),
}

# Create PDF
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 24)
        self.cell(0, 20, 'RouteCraft Project Portfolio Evidence', 0, 1, 'C')

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, 'Page ' + str(self.page_no()), 0, 0, 'C')

pdf = PDF()
pdf.add_page()

pdf.set_font('Arial', '', 12)
pdf.multi_cell(0, 10, 'Project: RouteCraft\nType: ML-Powered Multi-Modal Transit Planner\nLocation: Bengaluru, India\n\n'
                      'RouteCraft is an end-to-end Machine Learning and web application project that calculates '
                      'and ranks seven different transit variations (Walk, Cab, Auto, BMTC Bus, Metro) by cost '
                      'and travel time.\n\n'
                      'The following screenshots show the actual RouteCraft application running locally, demonstrating '
                      'its real-world multi-modal graph and ML-backed traffic predictions.')

# Add images to PDF
pdf.add_page()
pdf.set_font('Arial', 'B', 16)
pdf.cell(0, 10, 'Application Interface (Home)', 0, 1)
if os.path.exists(images['home']):
    pdf.image(images['home'], x=10, w=190)

pdf.add_page()
pdf.cell(0, 10, 'Search Results (Multi-Modal Routes)', 0, 1)
if os.path.exists(images['results']):
    pdf.image(images['results'], x=10, w=190)

pdf_path = os.path.join(out_dir, "RouteCraft_Evidence.pdf")
pdf.output(pdf_path, 'F')

print(f"Success! PDF generated at {pdf_path}")
