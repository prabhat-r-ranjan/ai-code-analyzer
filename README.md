# Java Microservice Migration Assessment Tool

**Automated Repository-Based Assessment for AWS EKS to Azure AKS Migration**

A Python-based assessment utility designed to analyze Java/Spring Boot microservices and their Kubernetes deployment configurations. The tool automates technical discovery, identifies potential dependencies, highlights migration considerations, and generates structured assessment outputs to support cloud migration planning.

The project is intended to reduce repetitive manual assessment activities across large portfolios of Java microservices.

## 1. Project Overview

Migrating Java microservices from Amazon EKS to Azure AKS requires a detailed understanding of each application's technology stack, configuration, APIs, integrations, Kubernetes resources, and dependencies.

Manual assessments typically involve inspecting source code, Maven dependencies, application properties, Kubernetes YAML manifests, and related configuration files.

This tool automates much of the initial repository-based discovery process.

### Key Objectives

- Automate Java microservice technical assessments.
- Discover technology stacks and application dependencies.
- Identify REST APIs and database configurations.
- Analyze Kubernetes deployment manifests.
- Correlate Kubernetes resources and application dependencies.
- Highlight potential migration risks and validation requirements.
- Generate structured JSON and Excel assessment outputs.
- Provide technical evidence for HLD and LLD preparation.
- Establish a foundation for future EKS runtime assessment.

**Current assessment scope:** Static analysis of Git repository content.

The tool does not currently perform live EKS cluster discovery, verify runtime connectivity, or automatically migrate applications.

---

## 2. High-Level Architecture

```text
                         User / Swagger UI
                                |
                                v
                         FastAPI Backend
                           app/main.py
                                |
                                v
                       Repository Analyzer
                         app/repository.py
                                |
                                v
                        Git Repository
                                |
                    Clone to Temporary Folder
                                |
                                v
                  Source & Configuration Analysis
                                |
          +---------------------+----------------------+
          |                     |                      |
          v                     v                      v
   Application Analysis   Configuration Analysis   Kubernetes Analysis
          |                     |                      |
   - Maven/POM            - Database Config       - Deployments
   - Java Version         - Integrations          - Services
   - Spring Boot          - Downstream Calls      - ConfigMaps
   - REST APIs                                    - Secrets
                                                 - HPA
                                                 - PVC
          |                     |                      |
          +---------------------+----------------------+
                                |
                                v
                       Dependency Correlation
                                |
                 +--------------+---------------+
                 |                              |
                 v                              v
          Kubernetes Resource          Application-to-Database
             Correlation                    Correlation
                 |                              |
                 +--------------+---------------+
                                |
                                v
                         Migration Findings
                                |
                                v
                         Assessment Results
                                |
                       +--------+--------+
                       |                 |
                       v                 v
                  JSON Response      Excel Workbook
```

### Assessment Workflow

1. User submits a Git repository URL and an optional branch.
2. The application validates the repository URL.
3. The repository is cloned into a temporary directory.
4. Individual analyzers inspect supported source and configuration files.
5. Kubernetes manifests are parsed into structured resource inventories.
6. Dependency correlation identifies potential relationships between resources.
7. Migration findings are generated for conditions requiring review.
8. Results are returned as JSON or passed to the Excel report generator.
9. Temporary repository files are cleaned up.

---

## 3. Technology Stack

| Component | Technology |
|---|---|
| Programming Language | Python |
| Backend Framework | FastAPI |
| API Documentation | Swagger UI / OpenAPI |
| Git Integration | GitPython |
| Java Build Analysis | Maven POM parsing |
| Source Code Analysis | Python-based static analyzers |
| Kubernetes Analysis | YAML manifest parsing |
| Excel Reporting | OpenPyXL |
| API Server | Uvicorn |
| Source Control | Git |

### Supported Assessment Areas

- Java and Spring Boot technology discovery
- Maven dependency analysis
- REST API discovery
- Database configuration analysis
- Supported integration pattern discovery
- Supported downstream HTTP client discovery
- Kubernetes manifest discovery
- Kubernetes resource dependency correlation
- Application-to-database dependency correlation
- Migration findings and assessment summaries

---

## 4. Project Structure

```text
ai-code-analyzer/
|
|-- app/
|   |-- main.py
|   |-- repository.py
|   |-- technology_analyzer.py
|   |-- technology_classifier.py
|   |-- api_analyzer.py
|   |-- database_analyzer.py
|   |-- integration_analyzer.py
|   |-- downstream_analyzer.py
|   |-- deployment_analyzer.py
|   |-- dependency_correlator.py
|   |-- application_dependency_analyzer.py
|   |-- excel_generator.py
|
|-- README.md
```

### Module Responsibilities

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI endpoints and assessment orchestration |
| `repository.py` | Git repository cloning and analyzer execution |
| `technology_analyzer.py` | Maven and technology extraction |
| `technology_classifier.py` | Technology categorization |
| `api_analyzer.py` | Spring REST API discovery |
| `database_analyzer.py` | Database configuration extraction |
| `integration_analyzer.py` | Supported integration discovery |
| `downstream_analyzer.py` | Supported outbound dependency discovery |
| `deployment_analyzer.py` | Kubernetes manifest analysis |
| `dependency_correlator.py` | Kubernetes resource dependency mapping |
| `application_dependency_analyzer.py` | Application-to-database dependency mapping |
| `excel_generator.py` | Excel assessment workbook generation |

---

## 5. Milestone Implementation Summary

### Milestone 1 — FastAPI Backend Foundation

**Status: Completed**

Established the Python FastAPI backend and health-check endpoint.

Implemented:

- FastAPI application initialization
- REST API foundation
- Swagger UI integration
- Application health endpoint

**Example:**

```http
GET /health
```

Response:

```json
{
  "status": "UP"
}
```

### Milestone 2 — Git Repository Integration

**Status: Completed**

Implemented repository cloning and temporary workspace management.

Features:

- HTTPS repository URL validation
- Optional branch selection
- GitPython-based cloning
- Temporary directory management
- Automatic cleanup after analysis

**Example input:**

```json
{
  "repo_url": "https://github.com/prabhat-r-ranjan/incident-management-system.git",
  "branch": null
}
```

### Milestone 3 — Maven and Technology Discovery

**Status: Completed**

Implemented Maven POM discovery and dependency extraction.

Extracted information includes:

- Maven POM files
- Java version
- Spring Boot version
- Maven dependencies
- Dependency coordinates

**Example discovered technologies:**

```text
Java: 17
Spring Boot: 3.1.5
Build Tool: Maven
Database Driver: PostgreSQL
```

### Milestone 4 — Technology Classification

**Status: Completed**

Added classification of Maven dependencies into technology categories.

Examples:

| Dependency | Category |
|---|---|
| Spring Boot Web | REST / Web |
| Spring Data JPA | Persistence / ORM |
| PostgreSQL Driver | Database |
| Spring Boot Actuator | Monitoring |
| Micrometer Prometheus | Metrics |

### Milestone 5 — REST API Discovery

**Status: Completed**

Implemented Spring controller and request-mapping analysis.

Identifies supported REST API declarations and HTTP methods.

**Example:**

```java
@RestController
@RequestMapping("/api/incidents")
public class IncidentController {

    @GetMapping("/{id}")
    public Incident getIncident(@PathVariable Long id) {
        return service.getIncident(id);
    }
}
```

Potential assessment output:

```text
Controller: IncidentController
Method: GET
Endpoint: /api/incidents/{id}
```

**Test repository result:** 22 REST endpoints discovered.

### Milestone 6 — Database Configuration Discovery

**Status: Completed**

Implemented database configuration discovery.

**Example configuration:**

```properties
spring.datasource.url=jdbc:postgresql://postgres:5432/incidentdb
```

Extracted information:

```text
Database Type: PostgreSQL
Host: postgres
Port: 5432
Database Name: incidentdb
```

### Milestone 7 — Integration Discovery

**Status: Initial implementation completed**

Implemented detection of supported integration patterns.

Potential integration categories include messaging and authentication-related configuration.

**Example:**

```properties
spring.kafka.bootstrap-servers=kafka:9092
```

**Test repository result:** No integrations detected by the current analyzer.

A zero result does not establish that no runtime integrations exist.

### Milestone 8 — Downstream Dependency Discovery

**Status: Initial implementation completed**

Implemented static discovery of supported Java outbound HTTP client patterns.

Examples include:

- RestTemplate
- WebClient
- Feign

**Illustrative code:**

```java
restTemplate.getForObject(
    "http://customer-service/api/customers/10",
    String.class
);
```

**Test repository result:** No downstream dependencies detected by the current analyzer.

Runtime traffic or dynamic configuration may reveal additional dependencies.

### Milestone 9 — Excel Report Generation

**Status: Initial implementation completed**

Implemented Excel report generation using OpenPyXL.

**Existing workbook sections:**

- Description
- Technologies
- Up & Down Stream
- Summary

The current generator produces the initial assessment workbook. Dedicated sheets for Kubernetes dependency mapping and migration findings are planned.

### Milestone 10 — Kubernetes Manifest Discovery

**Status: Completed**

Implemented discovery of Kubernetes YAML resources.

Supported discovered resource types include:

- Deployment
- Service
- ConfigMap
- Secret
- HorizontalPodAutoscaler
- PersistentVolumeClaim

The analyzer also processes additional Kubernetes resource types where supported.

### Milestone 11 — Detailed Kubernetes Configuration Extraction

**Status: Completed for currently supported fields**

Enhanced Kubernetes assessment to extract configuration details.

Examples:

```text
Deployment: incident-backend
Replicas: 1
Container Port: 8081

CPU Request: 100m
CPU Limit: 500m

Memory Request: 256Mi
Memory Limit: 512Mi

Liveness Probe: /actuator/health
Readiness Probe: /actuator/health
```

Other extracted information includes container images, Service selectors, environment references, pod labels, volumes, HPA configuration and PVC definitions.

### Milestone 12 — Kubernetes Dependency Correlation

**Status: Implemented; accuracy improvements ongoing**

Implemented static relationship discovery between Kubernetes resources.

Supported relationships include:

```text
Deployment -> ConfigMap
Deployment -> Secret
Deployment -> PVC
Service -> Workload
HPA -> Deployment
Ingress -> Service
```

The analyzer also produces migration findings such as:

```text
SERVICE_ACCOUNT_UNSPECIFIED
READINESS_PROBE_NOT_DECLARED
RESOURCE_REQUEST_INCOMPLETE
PVC_STORAGE_MIGRATION
MULTIPLE_MANIFEST_DEFINITIONS
```

Each finding includes supporting evidence and a migration review recommendation.

A finding is not necessarily a confirmed production defect.

### Milestone 13 — Application-to-Database Dependency Correlation

**Status: Initial implementation completed; refinement pending**

Implemented correlation between application database configuration and Kubernetes resources.

**New module:**

```text
app/application_dependency_analyzer.py
```

Example dependency chain:

```text
Spring Boot Application
        |
        | JDBC Configuration
        v
PostgreSQL Database
        |
        | postgres:5432
        v
Kubernetes Service
        |
        | Service Selector
        v
PostgreSQL Deployment Candidate
        |
        | Volume Reference
        v
PersistentVolumeClaim
```

**Test repository findings:**

- PostgreSQL configuration identified
- PostgreSQL Service definitions matched
- Candidate PostgreSQL Deployments identified
- PostgreSQL PVC discovered
- Duplicate manifest candidates detected

**Current limitations:**

- Multiple manifest definitions may represent alternative deployment configurations.
- Effective namespaces may not be known.
- The active Kustomize overlay or Helm release is not yet resolved.
- Workload-to-PVC correlation requires further refinement.
- Runtime connectivity is not verified.

---

## 6. Installation and Setup

### Prerequisites

Install:

- Python 3.10 or later
- Git
- pip
- A supported terminal or IDE

### Step 1 — Clone the Project

```bash
git clone <your-repository-url>
cd ai-code-analyzer
```

Replace the placeholder with the actual repository URL.

### Step 2 — Create a Virtual Environment

**Windows:**

```powershell
python -m venv .venv
.venv\Scripts\activate
```

**Linux/macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### Step 3 — Install Dependencies

If the project contains a maintained `requirements.txt`:

```bash
pip install -r requirements.txt
```

Otherwise, the known core dependencies can be installed with:

```bash
pip install fastapi uvicorn GitPython PyYAML openpyxl
```

Additional dependencies may be required by individual analyzers. Keep `requirements.txt` synchronized with the actual imports used in the project.

### Step 4 — Start the Application

From the project root:

```bash
python -m uvicorn app.main:app --reload
```

Expected local address:

```text
http://127.0.0.1:8000
```

### Step 5 — Open Swagger UI

```text
http://127.0.0.1:8000/docs
```

---

## 7. API Reference

### GET /health

Checks application availability.

**Example response:**

```json
{
  "status": "UP"
}
```

### POST /analyze

Runs repository-based assessment and returns JSON.

**Request:**

```json
{
  "repo_url": "https://github.com/prabhat-r-ranjan/incident-management-system.git",
  "branch": null
}
```

**Main response fields:**

```text
repository
branch
pom_files
pom_count
status
technologies
api_endpoints
api_count
database_details
database_count
integration_details
integration_count
downstream_details
downstream_count
deployment_details
deployment_count
dependency_relationships
migration_findings
assessment_summary
application_dependencies
```

### POST /analyze/excel

Runs repository assessment and returns an Excel workbook.

**Request:**

```json
{
  "repo_url": "https://github.com/prabhat-r-ranjan/incident-management-system.git",
  "branch": null
}
```

**Response:**

```text
Content-Type:
application/vnd.openxmlformats-officedocument.spreadsheetml.sheet

Filename:
migration-assessment.xlsx
```

---

## 8. Sample Assessment Results

The following results were observed while testing the tool against the Incident Management System repository.

| Assessment Metric | Observed Result |
|---|---|
| Maven POM Files | 1 |
| Java Version | 17 |
| Spring Boot Version | 3.1.5 |
| REST API Endpoints | 22 |
| Database Configurations | 1 |
| Database Type | PostgreSQL |
| Database Host | postgres |
| Database Port | 5432 |
| Kubernetes Manifest Definitions | 15 |
| Kubernetes Dependency Relationships | 10 (earlier Milestone 12 run) |
| Runtime Verified | No |

### Kubernetes Manifest Inventory

| Resource Type | Manifest Definitions |
|---|---:|
| Deployment | 6 |
| Service | 3 |
| Secret | 3 |
| ConfigMap | 1 |
| HorizontalPodAutoscaler | 1 |
| PersistentVolumeClaim | 1 |
| **Total** | **15** |

These counts represent scanned definitions and may include demo manifests or alternative deployment configurations.

### Example Application Configuration

```text
Application: incident-backend
Container Port: 8081

Database: PostgreSQL
Database Host: postgres
Database Port: 5432
Database Name: incidentdb

HPA Minimum Replicas: 1
HPA Maximum Replicas: 5
HPA CPU Target: 30%
```

### Example Database Dependency

```text
Application Configuration
        |
        v
PostgreSQL Host: postgres
        |
        v
Kubernetes Service: postgres
        |
        v
Candidate PostgreSQL Deployment
        |
        v
PVC: postgres-pvc
        |
        v
Requested Storage: 5Gi
```

The dependency chain is based on static repository evidence and requires runtime confirmation.

---

## 9. HLD and LLD Support

### HLD — High-Level Design

Assessment results can support:

- Application technology overview
- Logical component identification
- Database dependency identification
- Kubernetes resource architecture
- Application communication overview
- Migration dependency analysis
- Initial risks and prerequisites

### LLD — Low-Level Design

Assessment results can provide source configuration inputs for:

- Deployment configuration
- Container images and ports
- CPU and memory settings
- Liveness and readiness probes
- Service types, ports and selectors
- ConfigMap and Secret references
- HPA settings
- PVC configuration
- Database host and port details
- Kubernetes dependency mapping

### Important Distinction

The tool currently provides **HLD/LLD assessment inputs**, not complete, implementation-ready migration design documents.

A complete target-state LLD requires confirmed runtime information and Azure architecture decisions.

---

## 10. Migration Findings

The Kubernetes dependency analyzer identifies conditions that require additional review during migration planning.

Example categories:

| Finding | Assessment Purpose |
|---|---|
| Missing explicit ServiceAccount | Review workload identity requirements |
| Missing readiness probe | Review application rollout safety |
| Incomplete resource requests | Review AKS workload sizing |
| PVC storage migration | Assess Azure storage mapping |
| Multiple manifest definitions | Resolve active deployment configuration |
| Unresolved resource reference | Check effective manifests and runtime resources |

### Finding Interpretation

- **Info:** Useful technical observation.
- **Review:** Requires engineering assessment or validation.

The current findings should not be interpreted as an automated production readiness certification.

---

## 11. Current Limitations

The current tool performs static repository analysis.

It does not yet:

- Connect directly to live EKS clusters.
- Verify actual running Deployments or Services.
- Confirm runtime application-to-database connectivity.
- Identify all dynamically configured integrations.
- Resolve all Helm and Kustomize effective manifests.
- Confirm active namespaces for every resource.
- Distinguish all demo resources from production resources.
- Discover complete runtime upstream/downstream traffic.
- Generate a full target-state AKS HLD or LLD.
- Execute application migration or cutover.
- Automatically validate migration success.

### Security Considerations

The tool validates repository URLs and rejects credentials embedded in HTTPS URLs.

For the current implementation:

- Avoid submitting repository URLs containing secrets.
- Do not place repository access tokens in URLs.
- Review repository access and network permissions before enterprise deployment.
- Do not expose the assessment API publicly without appropriate authentication and authorization.
- Treat repository content and generated reports as potentially sensitive.
- Use approved credential management for future private repository integration.

Production security hardening remains a future activity.

---

## 12. Development Roadmap

### Milestone 13 — Correlation Refinement

**Status: In progress**

Planned improvements:

- Refine namespace-aware resource matching.
- Improve handling of duplicate manifest definitions.
- Associate PVCs with the specific workloads that reference them.
- Correlate application configuration and Kubernetes configuration more accurately.
- Validate findings against additional repositories.

### Milestone 14 — Enhanced Excel Reporting

**Status: Planned**

Proposed additional worksheets:

- HLD Summary
- LLD Configuration
- Kubernetes Resource Inventory
- Dependency Mapping
- Application-to-Database Mapping
- Migration Findings

### Future Enhancements

- Helm/Kustomize effective manifest analysis
- CI/CD workflow assessment
- EKS runtime discovery
- Runtime dependency validation
- AWS-to-Azure service and configuration mapping
- AKS migration readiness assessment
- Consolidated reporting across multiple microservices
- Assessment dashboard/UI
- Authentication and enterprise access controls

---

## 13. Expected Business Value

The tool is designed to reduce manual effort in assessing Java microservices during cloud migration programs.

Potential benefits include:

1. **Faster discovery:** Automates repeated source-code and configuration inspection.
2. **Consistency:** Applies the same assessment logic across repositories.
3. **Traceability:** Records source files and evidence for identified dependencies.
4. **Migration planning:** Provides structured technical inputs for HLD and LLD preparation.
5. **Scalability:** Establishes a foundation for assessing large microservice portfolios.
6. **Reduced documentation effort:** Generates reusable JSON and Excel outputs.

Actual time savings, coverage and accuracy must be measured through representative repository assessments.

---

## 14. Project Status

| Milestone | Description | Status |
|---|---|---|
| 1 | FastAPI Backend | Completed |
| 2 | Git Repository Integration | Completed |
| 3 | Maven Technology Discovery | Completed |
| 4 | Technology Classification | Completed |
| 5 | REST API Discovery | Completed |
| 6 | Database Discovery | Completed |
| 7 | Integration Discovery | Initial Implementation |
| 8 | Downstream Discovery | Initial Implementation |
| 9 | Excel Reporting | Initial Implementation |
| 10 | Kubernetes Manifest Discovery | Completed |
| 11 | Kubernetes Configuration Assessment | Completed |
| 12 | Kubernetes Dependency Correlation | Refinement Ongoing |
| 13 | Application Dependency Correlation | Refinement Ongoing |
| 14 | Enhanced Excel Reporting | Planned |

---

## 15. Conclusion

The Java Microservice Migration Assessment Tool provides an automated foundation for repository-based application discovery and Kubernetes configuration assessment.

Through Milestones 1–13, the project has evolved from basic repository analysis into a tool capable of identifying potential relationships between application configuration, Kubernetes resources, database services and storage dependencies.

The next development priorities are improving dependency correlation accuracy, enhancing assessment reporting, and extending discovery to live EKS environments.

**Long-term objective:** Build a reusable, evidence-based assessment utility that helps migration engineers and solution architects accelerate Java microservice migration planning from AWS EKS to Azure AKS.

### Milestone 16 — Deployment Selection and Evidence Discovery

**Status: Initial implementation completed; Helm and Kustomize resolution improvements ongoing**

Implemented repository-based deployment configuration discovery to distinguish Kubernetes manifest candidates from manifests referenced by deployment automation.

**Implemented capabilities:**

- Discover supported CI/CD deployment commands and Argo CD Application declarations.
- Identify Helm, Kustomize and CI/CD configuration files.
- Resolve supported static Kustomize resource references when a deployment entrypoint is identified.
- Identify Kubernetes manifests referenced by supported deployment entrypoints.
- Detect multiple candidate definitions of the same Kubernetes resource.
- Record deployment evidence and unresolved references.
- Preserve source-file traceability and deployment selection status.
- Avoid treating repository manifests as confirmed running cluster resources.

**New module:**

```text
app/deployment_selector.py
```

**Deployment approaches:**

1. **Helm + Argo CD:** Partial support for Argo CD Application source discovery and Helm configuration identification. Helm template rendering and effective resource resolution are pending.
2. **Kustomize:** Support for identifying base and overlay configurations and resolving supported static references. Automatic selection requires a detected deployment entrypoint.
3. **Raw Kubernetes manifests:** Basic support for static `kubectl apply`, `replace` and `create` references.

**Latest test repository findings:**

| Assessment Item | Result |
|---|---|
| CI/CD configuration discovered | 1 |
| Kustomize configurations discovered | 3 |
| Deployment entrypoints detected | 0 |
| Selected manifest files | 0 |
| PostgreSQL duplicate resource conflicts | 3 |
| Runtime verified | No |

**Discovered configurations:**

```text
.github/workflows/backend-ci.yml
k8s/base/kustomization.yaml
k8s/demo/kustomization.yaml
k8s/overlays/dev/kustomization.yaml
```

**Current deployment selection warning:**

```text
NO_DEPLOYMENT_ENTRYPOINT_FOUND
```

This warning indicates that no supported deployment entrypoint was detected. It does not establish that the application is undeployed.

**Deployment selection statuses:**

- `CANDIDATE_ONLY` — Manifest discovered without supported deployment selection evidence.
- `SELECTED_BY_SOURCE` — Manifest referenced by a detected deployment entrypoint.
- `runtime_verified: false` — Running cluster state has not been confirmed.

**Additional assessment response fields:**

```text
deployment_selection
deployment_entrypoints
deployment_selection_conflicts
deployment_selection_warnings
deployment_evidence_inventory
deployment_documentation_references
deployment_evidence_summary
runtime_verified
```

**Current limitations:**

- Helm templates are not rendered.
- Complete Argo CD Helm and Kustomize configuration resolution is pending.
- External deployment pipelines may not be visible in the analyzed repository.
- Kustomize overlays are not automatically considered active.
- Actual running Kubernetes resources cannot be verified through repository analysis alone.
- Duplicate manifest definitions remain unresolved without sufficient deployment evidence.

**Next milestone — Deployment Configuration Resolution**

Improve source-level analysis for both Helm + Argo CD and Kustomize deployment approaches, including environment-specific manifest mapping, source references, and unresolved deployment configurations.

The objective is to produce accurate, evidence-based source-state microservice LLD inputs without claiming runtime deployment verification.

Milestone 16.4: Kustomize base/overlay analysis और Helm + Argo CD source mapping.



Milestone 16.5: Environment-wise manifest selection और conflict resolution.



Milestone 17: Dependency correlation को selected manifest context से जोड़ना.



Milestone 18: Existing 8-sheet Excel workbook में deployment findings integrate करना, बिना frozen 12-column Kubernetes LLD format बदले.



Milestone 19: Multiple repositories पर testing और validation.



Milestone 20: Demo-ready backend, error handling और assessment quality improvements.