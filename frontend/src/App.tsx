import { useRef, useState } from "react";
import "./index.css";

const API_BASE = "http://127.0.0.1:8000";

type InputMode = "upload" | "url";

type Stage = {
  name: string;
  label: string;
  icon: string;
};

const stages: Stage[] = [
  { name: "input", label: "Input", icon: "↑" },
  { name: "detect", label: "Detect", icon: "⌕" },
  { name: "process", label: "Process", icon: "⚙" },
  { name: "extract", label: "Extract", icon: "⌁" },
  { name: "structure", label: "Structure", icon: "☷" },
  { name: "validate", label: "Validate", icon: "✓" },
  { name: "output", label: "Output", icon: "◆" },
];

function App() {
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [inputMode, setInputMode] = useState<InputMode>("upload");
  const [file, setFile] = useState<File | null>(null);
  const [mediaUrl, setMediaUrl] = useState("");

  const [dragging, setDragging] = useState(false);
  const [processing, setProcessing] = useState(false);

  const [jobId, setJobId] = useState("");
  const [jobStatus, setJobStatus] = useState("");
  const [activeStage, setActiveStage] = useState("input");

  /*
   * This contains the COMPLETE response from:
   *
   * GET /api/media/jobs/{job_id}/result
   *
   * Example:
   *
   * {
   *   job_id,
   *   status,
   *   result: {
   *      source_type,
   *      source,
   *      metadata,
   *      validation,
   *      normalized: {...}
   *   }
   * }
   */
  const [result, setResult] = useState<any>(null);

  const [error, setError] = useState("");
  const [showRaw, setShowRaw] = useState(false);

  /* ============================================================
     INPUT
  ============================================================ */

  const clearResult = () => {
    setResult(null);
    setJobId("");
    setJobStatus("");
    setActiveStage("input");
    setError("");
    setShowRaw(false);
  };

  const selectFile = (selectedFile: File) => {
    setFile(selectedFile);
    setMediaUrl("");
    clearResult();
  };

  const handleFileChange = (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const selectedFile = event.target.files?.[0];

    if (selectedFile) {
      selectFile(selectedFile);
    }
  };

  const handleDrop = (
    event: React.DragEvent<HTMLDivElement>
  ) => {
    event.preventDefault();
    setDragging(false);

    const droppedFile = event.dataTransfer.files?.[0];

    if (droppedFile) {
      selectFile(droppedFile);
    }
  };

  const switchInputMode = (mode: InputMode) => {
    setInputMode(mode);
    setFile(null);
    setMediaUrl("");
    clearResult();

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  /* ============================================================
     API HELPERS
  ============================================================ */

  const extractJobId = (data: any): string | null => {
    return (
      data?.job_id ??
      data?.job?.job_id ??
      data?.id ??
      data?.job?.id ??
      null
    );
  };

  const extractStatus = (data: any): string => {
    return String(
      data?.status ??
        data?.job_status ??
        data?.job?.status ??
        data?.processing?.status ??
        ""
    ).toLowerCase();
  };

  const getStageFromStatus = (status: string) => {
    switch (status) {
      case "queued":
        return "input";

      case "processing":
        return "process";

      case "completed":
      case "partial":
      case "cached":
        return "output";

      case "failed":
        return "process";

      default:
        return "process";
    }
  };

  /* ============================================================
     FETCH FINAL RESULT
  ============================================================ */

  const fetchFinalResult = async (id: string) => {
    const response = await fetch(
      `${API_BASE}/api/media/jobs/${id}/result`
    );

    if (!response.ok) {
      throw new Error(
        (await response.text()) ||
          "Unable to retrieve the processing result."
      );
    }

    const data = await response.json();

    /*
     * IMPORTANT:
     *
     * We store the COMPLETE backend response.
     *
     * Actual backend structure:
     *
     * data
     * └── result
     *     └── normalized
     */
    setResult(data);
    setJobStatus(
      String(data?.status ?? "completed").toLowerCase()
    );
    setActiveStage("output");
  };

  /* ============================================================
     POLLING
  ============================================================ */

  const pollJob = async (id: string) => {
    const maxAttempts = 180;

    for (
      let attempt = 0;
      attempt < maxAttempts;
      attempt++
    ) {
      const response = await fetch(
        `${API_BASE}/api/media/jobs/${id}`
      );

      if (!response.ok) {
        throw new Error(
          (await response.text()) ||
            "Unable to retrieve job status."
        );
      }

      const data = await response.json();

      const status = extractStatus(data);

      setJobStatus(status || "processing");
      setActiveStage(
        getStageFromStatus(status)
      );

      if (
        status === "completed" ||
        status === "partial" ||
        status === "cached"
      ) {
        await fetchFinalResult(id);
        return;
      }

      if (status === "failed") {
        throw new Error(
          data?.error ||
            data?.message ||
            data?.processing?.error ||
            "Media processing failed."
        );
      }

      await new Promise((resolve) =>
        setTimeout(resolve, 1000)
      );
    }

    throw new Error(
      "Processing is taking longer than expected."
    );
  };

  /* ============================================================
     PROCESS MEDIA
  ============================================================ */

  const processMedia = async () => {
    if (inputMode === "upload" && !file) {
      setError("Please select a media file first.");
      return;
    }

    if (
      inputMode === "url" &&
      !mediaUrl.trim()
    ) {
      setError("Please enter a media URL.");
      return;
    }

    setProcessing(true);
    setError("");
    setResult(null);
    setJobId("");
    setJobStatus("");
    setActiveStage("input");

    try {
      let response: Response;

      if (inputMode === "upload") {
        const formData = new FormData();

        formData.append(
          "file",
          file as File
        );

        response = await fetch(
          `${API_BASE}/api/media/upload`,
          {
            method: "POST",
            body: formData,
          }
        );
      } else {
        response = await fetch(
          `${API_BASE}/api/media/url`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              url: mediaUrl.trim(),
            }),
          }
        );
      }

      if (!response.ok) {
        throw new Error(
          (await response.text()) ||
            "Media ingestion failed."
        );
      }

      const data = await response.json();

      const id = extractJobId(data);

      /*
       * Normally the backend returns a job ID.
       */
      if (id) {
        setJobId(id);

        const status =
          extractStatus(data) || "queued";

        setJobStatus(status);
        setActiveStage(
          getStageFromStatus(status)
        );

        await pollJob(id);
        return;
      }

      /*
       * Fallback:
       * backend may return a completed result directly.
       */
      if (
        data?.result ||
        data?.normalized ||
        data?.document_id ||
        data?.media_type
      ) {
        setResult(data);
        setJobStatus("completed");
        setActiveStage("output");
        return;
      }

      throw new Error(
        "Backend response did not contain a job ID or processing result."
      );
    } catch (err) {
      console.error(err);

      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong while processing the media."
      );
    } finally {
      setProcessing(false);
    }
  };

  /* ============================================================
     RESET
  ============================================================ */

  const reset = () => {
    setFile(null);
    setMediaUrl("");
    setResult(null);
    setJobId("");
    setJobStatus("");
    setActiveStage("input");
    setProcessing(false);
    setError("");
    setShowRaw(false);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  /* ============================================================
     RESULT EXTRACTION
  ============================================================ */

  /*
   * Actual API:
   *
   * response.result
   * └── normalized
   *
   * These two helpers keep the JSX clean.
   */

  const pipelineResult =
    result?.result ?? result ?? {};

  const normalized =
    pipelineResult?.normalized ??
    pipelineResult?.document ??
    pipelineResult ??
    {};

  const source =
    normalized?.source ?? {};

  const metadata =
    normalized?.metadata ?? {};

  const validation =
    pipelineResult?.validation ??
    normalized?.extra?.validation ??
    {};

  const content =
    normalized?.content ?? {};

  const segments =
    Array.isArray(content?.segments)
      ? content.segments
      : [];

  const evidence =
    Array.isArray(content?.evidence)
      ? content.evidence
      : [];

  const topics =
    Array.isArray(content?.topics)
      ? content.topics
      : [];

  const structuredElements =
    Array.isArray(
      content?.structured_elements
    )
      ? content.structured_elements
      : [];

  const provenance =
    Array.isArray(normalized?.provenance)
      ? normalized.provenance
      : [];

  const artifacts =
    Array.isArray(
      normalized?.artifacts?.items
    )
      ? normalized.artifacts.items
      : [];

  const processingInfo =
    normalized?.processing ?? {};

  const processingStages =
    Array.isArray(
      processingInfo?.stages
    )
      ? processingInfo.stages
      : [];

  const summary =
    typeof content?.summary === "string"
      ? content.summary
      : "";

  /* ============================================================
     FORMATTING
  ============================================================ */

  const formatBytes = (
    bytes: number | undefined
  ) => {
    if (
      bytes === undefined ||
      bytes === null
    ) {
      return "Not available";
    }

    if (bytes < 1024) {
      return `${bytes} B`;
    }

    if (bytes < 1024 * 1024) {
      return `${(
        bytes / 1024
      ).toFixed(1)} KB`;
    }

    return `${(
      bytes /
      (1024 * 1024)
    ).toFixed(2)} MB`;
  };

  const humanize = (key: string) =>
    key
      .replace(/_/g, " ")
      .replace(
        /([a-z])([A-Z])/g,
        "$1 $2"
      )
      .replace(
        /\b\w/g,
        (letter) =>
          letter.toUpperCase()
      );

  const primitive = (value: any) => {
    if (
      value === null ||
      value === undefined
    ) {
      return "Not available";
    }

    if (
      typeof value === "boolean"
    ) {
      return value ? "Yes" : "No";
    }

    return String(value);
  };

  /* ============================================================
     GENERIC DETAIL RENDERER
  ============================================================ */

  const renderValue = (
    value: any
  ): React.ReactNode => {
    if (
      value === null ||
      value === undefined
    ) {
      return (
        <span className="muted">
          Not available
        </span>
      );
    }

    if (
      typeof value === "string" ||
      typeof value === "number" ||
      typeof value === "boolean"
    ) {
      return (
        <span>
          {primitive(value)}
        </span>
      );
    }

    if (Array.isArray(value)) {
      if (value.length === 0) {
        return (
          <span className="muted">
            None
          </span>
        );
      }

      return (
        <div className="nested-list">
          {value.map(
            (item, index) => (
              <div
                className="nested-item"
                key={index}
              >
                {renderValue(item)}
              </div>
            )
          )}
        </div>
      );
    }

    if (
      typeof value === "object"
    ) {
      const entries =
        Object.entries(value);

      if (!entries.length) {
        return (
          <span className="muted">
            None
          </span>
        );
      }

      return (
        <div className="detail-list">
          {entries.map(
            ([key, item]) => (
              <div
                className="detail-row"
                key={key}
              >
                <span className="detail-key">
                  {humanize(key)}
                </span>

                <div className="detail-value">
                  {renderValue(item)}
                </div>
              </div>
            )
          )}
        </div>
      );
    }

    return String(value);
  };

  /* ============================================================
     SECTION
  ============================================================ */

  const Section = ({
    eyebrow,
    title,
    description,
    children,
  }: {
    eyebrow: string;
    title: string;
    description?: string;
    children: React.ReactNode;
  }) => (
    <section className="content-section">
      <div className="content-section-header">
        <div>
          <span className="section-label">
            {eyebrow}
          </span>

          <h3>{title}</h3>

          {description && (
            <p>{description}</p>
          )}
        </div>
      </div>

      {children}
    </section>
  );

  /* ============================================================
     EMPTY
  ============================================================ */

  const Empty = ({
    children,
  }: {
    children: React.ReactNode;
  }) => (
    <div className="empty-state">
      {children}
    </div>
  );

  /* ============================================================
     RENDER
  ============================================================ */

  return (
    <div className="app">

      {/* ======================================================
          HEADER
      ====================================================== */}

      <header className="topbar">
        <div className="brand">
          <div className="brand-mark">
            ✦
          </div>

          <div>
            <div className="brand-name">
              Universal<span>AI</span>
            </div>

            <div className="brand-subtitle">
              Media Processing Pipeline
            </div>
          </div>
        </div>

        <div className="header-status">
          <span className="status-dot" />
          Pipeline Online
        </div>
      </header>

      <main className="container">

        {/* ====================================================
            HERO
        ==================================================== */}

        <section className="hero">
          <div className="eyebrow">
            UNIVERSAL MEDIA INTELLIGENCE
          </div>

          <h1>
            One pipeline.
            <br />
            <span>
              Every type of media.
            </span>
          </h1>

          <p>
            Upload a video, audio file,
            image or PDF, or provide a
            direct media URL. The pipeline
            detects, processes, extracts,
            structures and validates
            everything into one normalized
            result.
          </p>
        </section>

        {/* ====================================================
            PIPELINE
        ==================================================== */}

        <section className="pipeline-card">
          <div className="pipeline-header">
            <div>
              <span className="section-label">
                PROCESSING FLOW
              </span>

              <h2>
                Universal Pipeline
              </h2>
            </div>

            <div className="pipeline-badge">
              {processing
                ? (
                  jobStatus ||
                  "processing"
                ).toUpperCase()
                : result
                ? "COMPLETE"
                : "READY"}
            </div>
          </div>

          <div className="pipeline">
            {stages.map(
              (stage, index) => {
                const activeIndex =
                  stages.findIndex(
                    (item) =>
                      item.name ===
                      activeStage
                  );

                return (
                  <div
                    className="stage-wrapper"
                    key={stage.name}
                  >
                    <div
                      className={`stage ${
                        index <=
                        activeIndex
                          ? "stage-active"
                          : ""
                      } ${
                        stage.name ===
                        activeStage
                          ? "stage-current"
                          : ""
                      }`}
                    >
                      <div className="stage-icon">
                        {stage.icon}
                      </div>

                      <span>
                        {stage.label}
                      </span>
                    </div>

                    {index <
                      stages.length -
                        1 && (
                      <div
                        className={`stage-line ${
                          index <
                          activeIndex
                            ? "line-active"
                            : ""
                        }`}
                      />
                    )}
                  </div>
                );
              }
            )}
          </div>
        </section>

        {/* ====================================================
            INPUT
        ==================================================== */}

        {!result && (
          <section className="workspace">

            <div className="upload-panel">

              <div className="panel-heading">
                <div>
                  <span className="section-label">
                    INPUT
                  </span>

                  <h2>
                    Process your media
                  </h2>
                </div>

                <span className="format-note">
                  VIDEO · AUDIO · IMAGE · PDF
                </span>
              </div>

              <div className="input-tabs">
                <button
                  className={
                    inputMode ===
                    "upload"
                      ? "input-tab active"
                      : "input-tab"
                  }
                  onClick={() =>
                    switchInputMode(
                      "upload"
                    )
                  }
                >
                  ↑ Upload File
                </button>

                <button
                  className={
                    inputMode === "url"
                      ? "input-tab active"
                      : "input-tab"
                  }
                  onClick={() =>
                    switchInputMode(
                      "url"
                    )
                  }
                >
                  ↗ Media URL
                </button>
              </div>

              {inputMode ===
                "upload" && (
                <>
                  {!file && (
                    <div
                      className={`dropzone ${
                        dragging
                          ? "dragging"
                          : ""
                      }`}
                      onDragOver={(
                        event
                      ) => {
                        event.preventDefault();
                        setDragging(
                          true
                        );
                      }}
                      onDragLeave={() =>
                        setDragging(
                          false
                        )
                      }
                      onDrop={
                        handleDrop
                      }
                      onClick={() =>
                        fileInputRef.current?.click()
                      }
                    >
                      <div className="upload-icon">
                        ↑
                      </div>

                      <h3>
                        Drop your file here
                      </h3>

                      <p>
                        or{" "}
                        <strong>
                          browse from your
                          computer
                        </strong>
                      </p>

                      <div className="supported">
                        MP4 · MOV · MP3 · WAV ·
                        PNG · JPG · PDF
                      </div>

                      <input
                        ref={
                          fileInputRef
                        }
                        type="file"
                        hidden
                        accept="video/*,audio/*,image/*,application/pdf"
                        onChange={
                          handleFileChange
                        }
                      />
                    </div>
                  )}

                  {file && (
                    <div className="selected-file">
                      <div className="file-symbol">
                        FILE
                      </div>

                      <div className="file-info">
                        <h3>
                          {file.name}
                        </h3>

                        <div>
                          {file.type ||
                            "Media"}
                          {" • "}
                          {formatBytes(
                            file.size
                          )}
                        </div>
                      </div>

                      <button
                        className="remove-button"
                        onClick={
                          reset
                        }
                      >
                        Remove
                      </button>
                    </div>
                  )}
                </>
              )}

              {inputMode ===
                "url" && (
                <div className="url-input-area">
                  <input
                    type="url"
                    value={
                      mediaUrl
                    }
                    onChange={(
                      event
                    ) =>
                      setMediaUrl(
                        event.target
                          .value
                      )
                    }
                    placeholder="https://example.com/media/video.mp4"
                  />

                  <p>
                    Use a directly
                    accessible media
                    URL.
                  </p>
                </div>
              )}

              {!processing &&
                (file ||
                  mediaUrl.trim()) && (
                  <button
                    className="process-button"
                    onClick={
                      processMedia
                    }
                  >
                    <span>
                      Process Media
                    </span>

                    <span>
                      →
                    </span>
                  </button>
                )}

              {processing && (
                <div className="processing-box">
                  <div className="spinner" />

                  <div>
                    <strong>
                      Processing your
                      media...
                    </strong>

                    <span>
                      Pipeline status:{" "}
                      {jobStatus ||
                        "starting"}
                    </span>

                    {jobId && (
                      <span className="job-id">
                        Job ID: {jobId}
                      </span>
                    )}
                  </div>
                </div>
              )}

              {error && (
                <div className="error-box">
                  <strong>
                    Processing failed
                  </strong>

                  <span>
                    {error}
                  </span>

                  {jobId && (
                    <span>
                      Job ID: {jobId}
                    </span>
                  )}
                </div>
              )}
            </div>

            <aside className="capabilities">

              <span className="section-label">
                CAPABILITIES
              </span>

              <div className="capability">
                <div>◈</div>
                <section>
                  <strong>
                    Smart Detection
                  </strong>
                  <span>
                    Identifies the actual
                    media type before
                    processing.
                  </span>
                </section>
              </div>

              <div className="capability">
                <div>⌁</div>
                <section>
                  <strong>
                    Content Extraction
                  </strong>
                  <span>
                    OCR, transcription,
                    metadata and PDF
                    text extraction.
                  </span>
                </section>
              </div>

              <div className="capability">
                <div>☷</div>
                <section>
                  <strong>
                    Structured Output
                  </strong>
                  <span>
                    Converts different
                    media types into one
                    normalized schema.
                  </span>
                </section>
              </div>

              <div className="capability">
                <div>✓</div>
                <section>
                  <strong>
                    Validation
                  </strong>
                  <span>
                    Preserves validation,
                    warnings and errors.
                  </span>
                </section>
              </div>

              <div className="capability">
                <div>◆</div>
                <section>
                  <strong>
                    Provenance
                  </strong>
                  <span>
                    Extracted information
                    remains traceable to
                    its source.
                  </span>
                </section>
              </div>

            </aside>
          </section>
        )}

        {/* ====================================================
            RESULTS
        ==================================================== */}

        {result && (
          <section className="results">

            <div className="results-header">
              <div>
                <span className="section-label">
                  NORMALIZED OUTPUT
                </span>

                <h2>
                  Processing complete
                </h2>

                <p>
                  Complete deterministic
                  output from the universal
                  media pipeline.
                </p>
              </div>

              <button
                className="new-file-button"
                onClick={reset}
              >
                + Process another
              </button>
            </div>

            {/* ==================================================
                OVERVIEW
            ================================================== */}

            <div className="result-grid">

              <div className="result-card">
                <span>
                  MEDIA TYPE
                </span>

                <strong>
                  {String(
                    normalized?.media_type ??
                      pipelineResult?.metadata
                        ?.media_type ??
                      "Unknown"
                  ).toUpperCase()}
                </strong>
              </div>

              <div className="result-card">
                <span>
                  STATUS
                </span>

                <strong>
                  {String(
                    pipelineResult?.status ??
                      processingInfo?.status ??
                      jobStatus ??
                      "processed"
                  ).toUpperCase()}
                </strong>
              </div>

              <div className="result-card">
                <span>
                  DOCUMENT ID
                </span>

                <strong className="break">
                  {normalized?.document_id ??
                    "Not available"}
                </strong>
              </div>

              <div className="result-card">
                <span>
                  PAGES / SEGMENTS
                </span>

                <strong>
                  {segments.length}
                </strong>
              </div>

            </div>

            {/* ==================================================
                DOCUMENT
            ================================================== */}

            <Section
              eyebrow="01 · DOCUMENT"
              title="Normalized document"
              description="Core identity and schema information."
            >
              <div className="field-grid">

                <div>
                  <span>
                    Document ID
                  </span>
                  <strong>
                    {normalized?.document_id ??
                      "Not available"}
                  </strong>
                </div>

                <div>
                  <span>
                    Schema version
                  </span>
                  <strong>
                    {normalized?.schema_version ??
                      "Not available"}
                  </strong>
                </div>

                <div>
                  <span>
                    Media type
                  </span>
                  <strong>
                    {normalized?.media_type ??
                      "Not available"}
                  </strong>
                </div>

                <div>
                  <span>
                    Job ID
                  </span>
                  <strong>
                    {jobId ||
                      result?.job_id ||
                      "Not available"}
                  </strong>
                </div>

              </div>
            </Section>

            {/* ==================================================
                SOURCE
            ================================================== */}

            <Section
              eyebrow="02 · SOURCE"
              title="Source information"
              description="Information describing where the original media came from."
            >
              {Object.keys(source).length >
              0 ? (
                renderValue(source)
              ) : (
                <Empty>
                  No source information
                  was returned.
                </Empty>
              )}
            </Section>

            {/* ==================================================
                METADATA
            ================================================== */}

            <Section
              eyebrow="03 · METADATA"
              title="Media metadata"
              description="Technical information detected or recorded for the source."
            >
              {Object.keys(metadata).length >
              0 ? (
                renderValue(metadata)
              ) : (
                <Empty>
                  No metadata was
                  returned.
                </Empty>
              )}
            </Section>

            {/* ==================================================
                VALIDATION
            ================================================== */}

            <Section
              eyebrow="04 · VALIDATION"
              title="Validation result"
              description="Input validation and integrity checks performed by the pipeline."
            >
              {Object.keys(validation).length >
              0 ? (
                <div className="validation-grid">
                  {Object.entries(
                    validation
                  ).map(
                    ([key, value]) => (
                      <div
                        className="validation-item"
                        key={key}
                      >
                        <span>
                          {humanize(key)}
                        </span>

                        <strong
                          className={
                            typeof value ===
                              "boolean" &&
                            value
                              ? "success"
                              : ""
                          }
                        >
                          {primitive(
                            value
                          )}
                        </strong>
                      </div>
                    )
                  )}
                </div>
              ) : (
                <Empty>
                  No validation
                  information was
                  returned.
                </Empty>
              )}
            </Section>

            {/* ==================================================
                SUMMARY
            ================================================== */}

            <Section
              eyebrow="05 · SUMMARY"
              title="Pipeline summary"
              description="Summary returned as part of deterministic normalized content."
            >
              {summary ? (
                <div className="summary-box">
                  {summary}
                </div>
              ) : (
                <Empty>
                  No summary was
                  returned.
                </Empty>
              )}
            </Section>

            {/* ==================================================
                EXTRACTED TEXT / SEGMENTS
            ================================================== */}

            <Section
              eyebrow="06 · EXTRACTED CONTENT"
              title={`Content segments (${segments.length})`}
              description="Every extracted segment is displayed with its available source information."
            >
              {segments.length ===
              0 ? (
                <Empty>
                  No content segments
                  were returned.
                </Empty>
              ) : (
                <div className="segments">

                  {segments.map(
                    (
                      segment,
                      index
                    ) => (
                      <article
                        className="segment"
                        key={
                          segment?.evidence_id ??
                          index
                        }
                      >
                        <div className="segment-number">
                          {String(
                            index + 1
                          ).padStart(
                            2,
                            "0"
                          )}
                        </div>

                        <div className="segment-content">

                          <div className="segment-heading">
                            <strong>
                              {segment?.evidence_id ??
                                `Segment ${
                                  index +
                                  1
                                }`}
                            </strong>

                            {segment?.provenance
                              ?.page && (
                              <span>
                                Page{" "}
                                {
                                  segment
                                    .provenance
                                    .page
                                }
                              </span>
                            )}
                          </div>

                          {segment?.text && (
                            <div className="text-result">
                              {
                                segment.text
                              }
                            </div>
                          )}

                          <div className="segment-details">
                            {renderValue(
                              segment?.provenance ??
                                {}
                            )}
                          </div>

                          {segment?.confidence !==
                            undefined && (
                            <div className="confidence">
                              Confidence:{" "}
                              {
                                segment.confidence
                              }
                            </div>
                          )}

                        </div>
                      </article>
                    )
                  )}

                </div>
              )}
            </Section>

            {/* ==================================================
                EVIDENCE
            ================================================== */}

            <Section
              eyebrow="07 · EVIDENCE"
              title={`Evidence (${evidence.length})`}
              description="Evidence records associated with extracted content."
            >
              {evidence.length ===
              0 ? (
                <Empty>
                  No evidence records
                  were returned.
                </Empty>
              ) : (
                <div className="card-list">
                  {evidence.map(
                    (
                      item,
                      index
                    ) => (
                      <div
                        className="data-card"
                        key={
                          item?.evidence_id ??
                          index
                        }
                      >
                        <div className="data-card-title">
                          <strong>
                            {item?.evidence_id ??
                              `Evidence ${
                                index +
                                1
                              }`}
                          </strong>

                          <span>
                            {item?.content_type ??
                              "Evidence"}
                          </span>
                        </div>

                        {item?.text && (
                          <p>
                            {item.text}
                          </p>
                        )}

                        {renderValue(
                          item?.provenance ??
                            item
                        )}
                      </div>
                    )
                  )}
                </div>
              )}
            </Section>

            {/* ==================================================
                TOPICS
            ================================================== */}

            <Section
              eyebrow="08 · TOPICS"
              title={`Topics (${topics.length})`}
              description="Topics extracted and returned by the normalized deterministic result."
            >
              {topics.length ===
              0 ? (
                <Empty>
                  No topics were
                  returned.
                </Empty>
              ) : (
                <div className="topic-grid">
                  {topics.map(
                    (
                      topic,
                      index
                    ) => (
                      <div
                        className="topic-card"
                        key={index}
                      >
                        <span>
                          {String(
                            index + 1
                          ).padStart(
                            2,
                            "0"
                          )}
                        </span>

                        <h4>
                          {topic?.name ??
                            topic?.title ??
                            `Topic ${
                              index +
                              1
                            }`}
                        </h4>

                        <p>
                          {topic?.description ??
                            topic?.summary ??
                            "No description available."}
                        </p>
                      </div>
                    )
                  )}
                </div>
              )}
            </Section>

            {/* ==================================================
                STRUCTURED ELEMENTS
            ================================================== */}

            <Section
              eyebrow="09 · STRUCTURE"
              title={`Structured elements (${structuredElements.length})`}
              description="Structured information detected during media extraction."
            >
              {structuredElements.length ===
              0 ? (
                <Empty>
                  No structured
                  elements were
                  returned for this
                  media.
                </Empty>
              ) : (
                renderValue(
                  structuredElements
                )
              )}
            </Section>

            {/* ==================================================
                PROVENANCE
            ================================================== */}

            <Section
              eyebrow="10 · PROVENANCE"
              title={`Source provenance (${provenance.length})`}
              description="Traceability information connecting extracted data back to the original source."
            >
              {provenance.length ===
              0 ? (
                <Empty>
                  No provenance
                  records were
                  returned.
                </Empty>
              ) : (
                <div className="card-list">
                  {provenance.map(
                    (
                      item,
                      index
                    ) => (
                      <div
                        className="data-card"
                        key={index}
                      >
                        <div className="data-card-title">
                          <strong>
                            Source{" "}
                            {index + 1}
                          </strong>

                          <span>
                            {item?.source_type ??
                              "source"}
                          </span>
                        </div>

                        {renderValue(
                          item
                        )}
                      </div>
                    )
                  )}
                </div>
              )}
            </Section>

            {/* ==================================================
                PROCESSING
            ================================================== */}

            <Section
              eyebrow="11 · PROCESSING"
              title="Processing state"
              description="Complete processing information recorded by the normalized document."
            >
              {Object.keys(
                processingInfo
              ).length > 0 ? (
                <>
                  <div className="field-grid">
                    <div>
                      <span>
                        Status
                      </span>
                      <strong>
                        {processingInfo.status ??
                          "Not available"}
                      </strong>
                    </div>

                    <div>
                      <span>
                        Cache hit
                      </span>
                      <strong>
                        {processingInfo.cache_hit
                          ? "Yes"
                          : "No"}
                      </strong>
                    </div>

                    <div>
                      <span>
                        Warnings
                      </span>
                      <strong>
                        {Array.isArray(
                          processingInfo.warnings
                        )
                          ? processingInfo
                              .warnings
                              .length
                          : 0}
                      </strong>
                    </div>

                    <div>
                      <span>
                        Errors
                      </span>
                      <strong>
                        {Array.isArray(
                          processingInfo.errors
                        )
                          ? processingInfo
                              .errors
                              .length
                          : 0}
                      </strong>
                    </div>
                  </div>

                  <h4 className="subheading">
                    Processing stages
                  </h4>

                  {processingStages.length ===
                  0 ? (
                    <Empty>
                      No individual
                      processing stages
                      were returned.
                    </Empty>
                  ) : (
                    <div className="stage-results">
                      {processingStages.map(
                        (
                          stage,
                          index
                        ) => (
                          <div
                            className="stage-result"
                            key={
                              index
                            }
                          >
                            <div>
                              <strong>
                                {stage?.name ??
                                  `Stage ${
                                    index +
                                    1
                                  }`}
                              </strong>

                              <span>
                                {stage?.status ??
                                  "unknown"}
                              </span>
                            </div>

                            {stage?.message && (
                              <p>
                                {
                                  stage.message
                                }
                              </p>
                            )}

                            {stage?.metadata && (
                              <div>
                                {renderValue(
                                  stage.metadata
                                )}
                              </div>
                            )}
                          </div>
                        )
                      )}
                    </div>
                  )}
                </>
              ) : (
                <Empty>
                  No processing
                  information was
                  returned.
                </Empty>
              )}
            </Section>

            {/* ==================================================
                ARTIFACTS
            ================================================== */}

            <Section
              eyebrow="12 · ARTIFACTS"
              title={`Generated artifacts (${artifacts.length})`}
              description="Derived files generated during media processing."
            >
              {artifacts.length ===
              0 ? (
                <Empty>
                  No artifacts were
                  returned.
                </Empty>
              ) : (
                <div className="card-list">
                  {artifacts.map(
                    (
                      artifact,
                      index
                    ) => (
                      <div
                        className="data-card"
                        key={index}
                      >
                        <div className="data-card-title">
                          <strong>
                            {artifact?.filename ??
                              artifact?.file_path ??
                              artifact?.path ??
                              `Artifact ${
                                index +
                                1
                              }`}
                          </strong>

                          <span>
                            {artifact?.artifact_type ??
                              artifact?.mime_type ??
                              "Artifact"}
                          </span>
                        </div>

                        <div className="artifact-meta">
                          {artifact?.size_bytes !==
                            undefined && (
                            <span>
                              Size:{" "}
                              {formatBytes(
                                artifact.size_bytes
                              )}
                            </span>
                          )}

                          {artifact?.content_hash && (
                            <span>
                              Hash:{" "}
                              {
                                artifact.content_hash
                              }
                            </span>
                          )}

                          {artifact?.file_path && (
                            <span>
                              Path:{" "}
                              {
                                artifact.file_path
                              }
                            </span>
                          )}
                        </div>
                      </div>
                    )
                  )}
                </div>
              )}
            </Section>

            {/* ==================================================
                EXTRA
            ================================================== */}

            {normalized?.extra && (
              <Section
                eyebrow="13 · ADDITIONAL DATA"
                title="Additional normalized information"
                description="Additional information preserved by the pipeline."
              >
                {renderValue(
                  normalized.extra
                )}
              </Section>
            )}

            {/* ==================================================
                RAW JSON
            ================================================== */}

            <Section
              eyebrow="14 · RAW OUTPUT"
              title="Complete API response"
              description="The complete response returned by the backend."
            >
              <button
                className="text-button"
                onClick={() =>
                  setShowRaw(
                    (value) => !value
                  )
                }
              >
                {showRaw
                  ? "Hide raw JSON"
                  : "Inspect raw JSON"}
              </button>

              {showRaw && (
                <pre className="raw-json">
                  {JSON.stringify(
                    result,
                    null,
                    2
                  )}
                </pre>
              )}
            </Section>

            {/* ==================================================
                FOOTER ACTION
            ================================================== */}

            <div className="result-footer">
              <button
                className="new-file-button"
                onClick={reset}
              >
                Process another media file
              </button>

              {jobId && (
                <span>
                  Processing job: {jobId}
                </span>
              )}
            </div>

          </section>
        )}

      </main>

      <footer>
        <span>
          Universal AI Media Processing Pipeline
        </span>

        <span>
          Deterministic · Structured ·
          Provenance-aware
        </span>
      </footer>

    </div>
  );
}

export default App;