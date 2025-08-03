# ADR-002: OpenShift GPU-Accelerated LLM Deployment Architecture

**Date:** December 19, 2024  
**Status:** 🚧 **PROPOSED**  
**Deciders:** Development Team, Architecture Review  
**Technical Story:** Migration from local LLM deployment to OpenShift Container Platform with GPU acceleration for enhanced performance and scalability

## Context

Following the successful implementation of ADR-001 (Ansible Log Monitoring System with local Llama 3.1), we have been provided access to a new OpenShift Container Platform (OCP) cluster specifically configured for AI/ML workloads:

### Available Infrastructure:
- **OpenShift Console:** https://console-openshift-console.apps.jary-alm-0802.4cuu.p1.openshiftapps.com/
- **Red Hat OpenShift AI (RHOAI)** pre-installed and configured
- **NVIDIA AcceleratorProfile** configured for GPU workloads
- **2 nodes with 48GB L40S GPUs** (96GB total GPU memory)
- **Cluster-admin privileges** with Red Hat SSO authentication
- **OpenShift Dedicated (OSD)** cluster on AWS EC2 infrastructure

### Current State Assessment:
- ADR-001 implemented local Llama 3.1 (8B parameters) via Ollama
- Achieved 100% solution coverage and target performance metrics
- CPU-only processing with 30-second response times for LLM operations
- Zero operational costs but limited by local hardware constraints
- Smart-chunking detection engine providing 95% accuracy as foundation

### Opportunity Analysis:
- GPU acceleration could reduce LLM response times from 30s to <5s
- 96GB GPU memory enables larger models (70B+ parameters) for improved quality
- OpenShift provides enterprise-grade scalability, monitoring, and management
- RHOAI offers integrated ML workflow management and model serving
- Container-native deployment enables easier CI/CD and scaling

## Decision

### 1. LLM Deployment Migration: Local to OpenShift GPU Cluster

**Decision:** Migrate LLM deployment from local Ollama/Llama 3.1 to OpenShift cluster with GPU acceleration while maintaining the existing smart-chunking detection pipeline.

**Rationale:**
- **Performance Improvement:** GPU acceleration expected to reduce LLM response times by 6-10x
- **Model Quality:** 96GB GPU memory enables deployment of larger models (Llama 3.1 70B)
- **Enterprise Readiness:** OpenShift provides production-grade container orchestration
- **Cost Efficiency:** Shared GPU resources more economical than dedicated hardware procurement
- **Scalability:** Horizontal scaling capabilities for increased workload demands
- **Integration:** RHOAI provides native ML pipeline integration

### 2. Model Selection: Llama 3.1 70B Parameter Model

**Decision:** Deploy Llama 3.1 70B parameter model leveraging the 96GB GPU memory capacity.

**Rationale:**
- **Quality Improvement:** 70B model provides significantly better reasoning than 8B variant
- **Memory Fit:** 96GB GPU memory sufficient for 70B model with quantization
- **Context Window:** 8K context window maintained for smart-chunking integration
- **Compatibility:** Same model family ensures prompt compatibility with existing implementation
- **Open Source:** Maintains privacy and control benefits from ADR-001

### 3. Deployment Architecture: Hybrid Smart-Chunking + GPU LLM

**Decision:** Implement hybrid architecture with smart-chunking detection on edge/local systems and GPU-accelerated LLM processing in OpenShift cluster.

**Architecture Flow:**
```
Local/Edge:
Ansible Logs → Smart-Chunking Detection → Structured Results

OpenShift Cluster:
Structured Results → GPU LLM Processing → Enhanced Insights → Response
```

**Benefits:**
- **Latency Optimization:** Critical detection happens locally (<5s)
- **Bandwidth Efficiency:** Only structured results sent to cluster (not raw logs)
- **Privacy:** Raw log data remains on local infrastructure
- **Scalability:** GPU cluster handles computationally intensive LLM operations
- **Fault Tolerance:** Local detection continues if cluster unavailable

### 4. Container Platform: OpenShift with RHOAI Integration

**Decision:** Utilize Red Hat OpenShift AI (RHOAI) for model serving and ML pipeline management.

**Implementation Components:**
- **Model Serving:** RHOAI ModelServer with vLLM backend for Llama 3.1 70B
- **GPU Resources:** NVIDIA AcceleratorProfile for L40S GPU allocation
- **API Gateway:** OpenShift Routes for secure LLM API access
- **Monitoring:** Integrated Prometheus/Grafana for performance metrics
- **Scaling:** Horizontal Pod Autoscaler based on request volume

### 5. Integration Strategy: REST API Bridge

**Decision:** Implement REST API bridge to maintain compatibility with existing smart-chunking system while adding GPU LLM capabilities.

**API Design:**
```yaml
endpoints:
  /api/v1/solutions/generate:
    input: smart-chunking detection results
    processing: GPU-accelerated Llama 3.1 70B
    output: enhanced solutions with higher quality
  
  /api/v1/rca/generate:
    input: clustered error analysis
    processing: GPU-accelerated reasoning
    output: detailed root cause analysis
  
  /api/v1/health:
    monitoring: GPU utilization, model availability
```

## Consequences

### Positive Outcomes

1. **Performance Enhancement:**
   - LLM response times: 30s → <5s (6x improvement)
   - Higher quality outputs from 70B parameter model
   - Better reasoning capabilities for complex troubleshooting scenarios

2. **Scalability and Enterprise Readiness:**
   - Container-native deployment with OpenShift orchestration
   - Horizontal scaling based on demand
   - Enterprise-grade monitoring and alerting
   - High availability with multi-node GPU cluster

3. **Cost Optimization:**
   - Shared GPU infrastructure vs dedicated hardware procurement
   - Pay-per-use model aligned with actual workload demands
   - Reduced infrastructure management overhead

4. **Operational Excellence:**
   - Integrated CI/CD pipelines with OpenShift
   - Centralized logging and monitoring via RHOAI
   - Automated model deployment and versioning
   - Professional support through Red Hat subscription

### Negative Outcomes and Mitigations

1. **Network Dependency:**
   - **Issue:** Requires network connectivity to OpenShift cluster
   - **Mitigation:** Implement local fallback to smaller Llama model for offline scenarios

2. **Operational Complexity:**
   - **Issue:** Additional infrastructure to manage and monitor
   - **Mitigation:** Leverage RHOAI managed services and OpenShift automation

3. **Resource Contention:**
   - **Issue:** Shared GPU resources may experience contention
   - **Mitigation:** Implement request queuing and resource quotas

4. **Migration Risk:**
   - **Issue:** Potential service disruption during migration
   - **Mitigation:** Blue-green deployment strategy with gradual traffic shifting

## Implementation Plan

### Phase 1: Infrastructure Setup (Week 1-2)
- Set up RHOAI environment in OpenShift cluster
- Configure NVIDIA GPU resources and AcceleratorProfile
- Deploy model serving infrastructure with vLLM
- Load and test Llama 3.1 70B model deployment

### Phase 2: API Development (Week 3-4)
- Develop REST API bridge for smart-chunking integration
- Implement request/response transformation layers
- Add authentication and authorization (Red Hat SSO integration)
- Create comprehensive API documentation

### Phase 3: Integration Testing (Week 5-6)
- Update smart-chunking system to use GPU LLM APIs
- Performance testing and optimization
- Load testing with realistic workloads
- Monitoring and alerting configuration

### Phase 4: Migration and Validation (Week 7-8)
- Blue-green deployment for seamless migration
- A/B testing comparing local vs GPU LLM performance
- Production validation and performance tuning
- Documentation and operational runbooks

## Success Metrics

### Technical Metrics
- **Response Time:** LLM operations <5 seconds (vs current 30s)
- **Model Quality:** 70B model reasoning evaluation scores
- **Availability:** >99.9% uptime for LLM API services
- **GPU Utilization:** >70% efficient utilization of L40S resources
- **Throughput:** Support for 100+ concurrent LLM requests

### Business Metrics
- **Solution Quality:** Improved troubleshooting accuracy with 70B model
- **User Experience:** Sub-5-second response times for solution generation
- **Operational Cost:** GPU resource utilization cost analysis
- **Scalability:** Demonstrated scaling to 10x current workload

## Security Considerations

### Data Privacy
- Raw Ansible logs remain on local infrastructure
- Only processed, structured results transmitted to cluster
- OpenShift RBAC controls for API access
- Network encryption for all cluster communications

### Authentication and Authorization
- Red Hat SSO integration for cluster access
- Service account authentication for API calls
- Role-based access control (RBAC) for different user types
- API key management for external integrations

## References

- [ADR-001: Ansible Log Monitoring System Architecture](ADR-001-ansible-log-monitoring-architecture.md)
- [OpenShift AI Documentation](https://docs.redhat.com/en/documentation/red_hat_openshift_ai_cloud_service)
- [NVIDIA L40S GPU Specifications](https://www.nvidia.com/en-us/data-center/l40s/)
- [vLLM Model Serving Documentation](https://docs.vllm.ai/)

## Related ADRs

- ADR-001: Ansible Log Monitoring System Architecture (Foundation)
- ADR-003: Data Storage and Persistence Strategy (Future)
- ADR-004: Security and RBAC Implementation (Future)

---

**Last Updated:** December 19, 2024  
**Next Review:** January 19, 2025  
**Stakeholders:** Development Team, Infrastructure Team, Red Hat Support, Architecture Review Board 