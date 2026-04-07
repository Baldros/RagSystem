create extension if not exists vector;

create table if not exists crawl_runs (
    run_id text primary key,
    collection_name text not null,
    started_at timestamptz not null,
    seed_urls jsonb not null,
    notes text not null default ''
);

create table if not exists raw_documents (
    collection_name text not null,
    canonical_url text not null,
    source_url text not null,
    title text not null,
    html text not null,
    text_content text not null,
    markdown_content text not null,
    http_status integer not null,
    content_hash text not null,
    fetched_at timestamptz not null,
    metadata jsonb not null default '{}'::jsonb,
    primary key (collection_name, canonical_url)
);

create table if not exists discovered_nodes (
    collection_name text not null,
    node_id text not null,
    canonical_url text not null,
    url text not null,
    title text not null,
    source text not null,
    depth integer not null,
    parent_node_id text null,
    parent_canonical_url text null,
    toc_level integer null,
    toc_order integer null,
    doc_version text null,
    metadata jsonb not null default '{}'::jsonb,
    primary key (collection_name, node_id),
    unique (collection_name, canonical_url)
);

create table if not exists sections (
    collection_name text not null,
    section_id text not null,
    canonical_url text not null,
    heading text not null,
    level integer not null,
    order_in_page integer not null,
    text text not null,
    metadata jsonb not null default '{}'::jsonb,
    primary key (collection_name, section_id),
    foreign key (collection_name, canonical_url)
        references raw_documents(collection_name, canonical_url)
        on delete cascade
);

create table if not exists chunks (
    collection_name text not null,
    chunk_id text not null,
    section_id text not null,
    canonical_url text not null,
    order_in_section integer not null,
    text text not null,
    token_estimate integer not null,
    metadata jsonb not null default '{}'::jsonb,
    embedding vector(384),
    search_vector tsvector generated always as (to_tsvector('english', coalesce(text, ''))) stored,
    primary key (collection_name, chunk_id),
    foreign key (collection_name, section_id)
        references sections(collection_name, section_id)
        on delete cascade,
    foreign key (collection_name, canonical_url)
        references raw_documents(collection_name, canonical_url)
        on delete cascade
);

create table if not exists retrieval_traces (
    trace_id bigserial primary key,
    collection_name text not null,
    query text not null,
    created_at timestamptz not null,
    lexical_hits jsonb not null,
    vector_hits jsonb not null,
    fused_hits jsonb not null
);

create index if not exists idx_raw_documents_collection_name on raw_documents (collection_name);
create index if not exists idx_discovered_nodes_collection_name on discovered_nodes (collection_name);
create index if not exists idx_discovered_nodes_collection_parent on discovered_nodes (collection_name, parent_node_id);
create index if not exists idx_discovered_nodes_collection_canonical_url on discovered_nodes (collection_name, canonical_url);
create index if not exists idx_sections_collection_name_canonical_url on sections (collection_name, canonical_url);
create index if not exists idx_chunks_collection_name_canonical_url on chunks (collection_name, canonical_url);
create index if not exists idx_chunks_collection_name_section_id on chunks (collection_name, section_id);
create index if not exists idx_chunks_search_vector on chunks using gin (search_vector);
