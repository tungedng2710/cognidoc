The **Parser** receives curated page images from the Curator module. Each input page has already been preprocessed, for example by rotation correction, denoising, enhancement, page splitting, and document-type classification.

The Parser works at the **page level**, but all pages from the same multi-page document are grouped under a shared **document session**. During parsing, the system does not only generate markdown, HTML, or plain text. It also stores detailed structured information about detected elements, such as tables, figures, charts, text blocks, coordinates, reading order, logical cells, page index, and visual grounding metadata, into a **session database**.

This allows downstream extraction agents to reason over both the textual content and the visual structure of the document.

```mermaid
flowchart TD
    A[Curated Document Session] --> B[Page Iterator]

    B --> C[Input Page Image<br/>rotation-corrected, denoised, enhanced]

    C --> D[Step 1: Layout Detection]
    D --> E[Detect Regions<br/>text blocks, tables, figures, charts, headers, footers]
    E --> F[Reading Order Recognition]

    F --> G[Page Layout Graph]
    G --> H{Region Type Router}

    H --> I[OCR Text Block Processor]
    H --> J[Table Recognition Processor]
    H --> K[Chart / Graph / Figure Processor]

    I --> I1[OCR + Text Line Detection]
    I1 --> I2[Paragraph Reconstruction]
    I2 --> I3[Text Block Markdown]

    J --> J1[Table Structure Recognition]
    J1 --> J2[Cell Detection and Spanning]
    J2 --> J3[Logical Cell Reconstruction]
    J3 --> J4[Table Markdown / HTML / JSON]

    K --> K1[Figure / Chart Classification]
    K1 --> K2[Caption Association]
    K2 --> K3[Visual Summary or Metadata]
    K3 --> K4[Figure Record]

    I3 --> L[Page-level Representation]
    J4 --> L
    K4 --> L

    L --> M[Assemble Page Markdown / HTML]
    L --> N[Save Element Metadata]
```