```
oc-dynamic-agent-patterns on  main [!] is 📦 v0.1.0 via 🐍 v3.12.8 on ☁️  (us-west-2) on ☁️  mofoster
❯ oc get agents
NAME                    CLASS   VERSION   PHASE   URL                                                                                        AGE
app-perf-monitor        a2a     1.0.0     Ready   https//<redacted>.com        2d
cicd-pipeline-monitor   a2a     1.0.0     Ready   https//<redacted>.com   2d1h
k8-cluster-mon          a2a     1.0.0     Ready   https//<redacted>.com          29m
message-queue-monitor   a2a     1.0.0     Ready   https//<redacted>.com   2d1h

oc-dynamic-agent-patterns on  main [!] is 📦 v0.1.0 via 🐍 v3.12.8 on ☁️  (us-west-2) on ☁️  mofoster
❯ oc describe agent app-perf-monitor
Name:         app-perf-monitor
Namespace:    oc-dynamic-agents
Labels:       ai.openshift.io/agent.class=a2a
              app.kubernetes.io/managed-by=agent-controller
Annotations:  <none>
API Version:  ai.openshift.io/v1
Kind:         Agent
Metadata:
  Creation Timestamp:  2025-09-24T15:32:44Z
  Generation:          3
  Resource Version:    51060036
  UID:                 74898450-6816-4a04-91a8-d52c60c5bea0
Spec:
  Class:     a2a
  Endpoint:  /.well-known/agent.json
  Name:      app-perf-monitor
  Source Ref:
    API Version:  v1
    Kind:         Service
    Name:         app-perf-monitor-service
    Namespace:    oc-dynamic-agents
Status:
  Agent Card:
    Capabilities:
    Default Input Modes:
      text/plain
      application/json
    Default Output Modes:
      text/plain
      application/json
    Description:          Monitors application performance metrics, identifies bottlenecks, and provides optimization recommendations for cloud-native applications.
    Name:                 Application Performance Monitor
    Preferred Transport:  JSONRPC
    Protocol Version:     0.3.0
    Skills:
      Description:  Analyze application performance metrics and identify bottlenecks
      Id:           performance-analysis
      Input Modes:
        text/plain
        application/json
      Name:  Performance Analysis
      Output Modes:
        text/plain
        application/json
      Tags:
        performance
        monitoring
        analysis
      Description:  Detect memory leaks and garbage collection issues
      Id:           memory-analysis
      Input Modes:
        text/plain
        application/json
      Name:  Memory Analysis
      Output Modes:
        text/plain
        application/json
      Tags:
        memory
        gc
        leak-detection
    URL:      https//<redacted>.com
    Version:  1.0.0
  Last Seen:  2025-09-24T15:33:00.895479+00:00
  Phase:      Ready
  URL:        https//<redacted>.com
Events:       <none>

oc-dynamic-agent-patterns on  main [!] is 📦 v0.1.0 via 🐍 v3.12.8 on ☁️  (us-west-2) on ☁️  mofoster
❯ claude
╭─────────────────────────────────────────────────────────────╮
│ ✻ Welcome to Claude Code!                                   │
│                                                             │
│   /help for help, /status for your current setup            │
│                                                             │
│   cwd: /Users/mofoster/Workspace/oc-dynamic-agent-patterns  │
╰─────────────────────────────────────────────────────────────╯


 What's new:
  • Enable /context command for Bedrock and Vertex
  • Add mTLS support for HTTP-based OpenTelemetry exporters
  • Set `CLAUDE_BASH_NO_LOGIN` environment variable to 1 or true to to skip login shell for BashTool
  • Fix Bedrock and Vertex environment variables evaluating all strings as truthy
  • No longer inform Claude of the list of allowed tools when permission is denied

> Hi could you list the agents available to me in my cluster?

⏺ I'll list the agents available in your OpenShift cluster.

⏺ oc-agent-bridge - discover_agents (MCP)(all_namespaces: true, verify_endpoints: true)
  ⎿  Found 4 agent(s) in all namespaces:

     [
     … +45 lines (ctrl+o to expand)

⏺ You have 4 agents available in your cluster, all in the oc-dynamic-agents namespace:

  1. app-perf-monitor - Monitors application performance metrics and provides optimization recommendations
  2. cicd-pipeline-monitor - Monitors CI/CD pipelines and tracks build success rates
  3. k8-cluster-mon - Monitors Kubernetes cluster health and resource utilization
  4. message-queue-monitor - Monitors message queue performance and throughput

  All agents are in "Ready" phase with accessible endpoints.

> Oh great, I've been having issues with my message queue. Can you ask the agent in charge of that to look at it?

⏺ I'll send a message to the message queue monitor agent to look at your message queue issues.

⏺ oc-agent-bridge - send_message_to_agent (MCP)(agent_url: "https//<redacted>.com", message: "The user is experiencing issues with their message queue. Can you analyze the current state of the message queue system and identify any problems or bottlenecks?")
  ⎿  Response from https//<redacted>.com:

     {
     … +26 lines (ctrl+o to expand)

⏺ The message queue monitor agent has identified several critical issues with your message queue system:

  Critical Issues Found:

  Status: CRITICAL (Score: 0.58/1.0)

  Immediate Problems:

  1. Severe Queue Backlog - Order processing queue has 45k messages (threshold: 10k)
  2. Poison Messages - Malformed JSON causing repeated failures (message ID: 7f8a9b2c)
  3. Consumer Offline - Email notification consumer down due to SMTP connection issues
  4. Memory Pressure - Node rmq-02 at 92% memory usage

  Key Metrics:

  - Total messages: 89,420
  - Publish rate: 520/sec vs Consume rate: 380/sec (140/sec deficit)
  - Memory usage: 87%
  - Consumer utilization: only 34.2%

  Immediate Actions Recommended:

  1. Purge poison message 7f8a9b2c and set up dead letter queue
  2. Scale order processing consumers from 6 to 12 instances
  3. Restart email notification consumer and fix SMTP connectivity
  4. Add memory to rmq-02 or rebalance queues

  The system is consuming slower than producing, creating a growing backlog that needs immediate attention.


oc-dynamic-agent-patterns on  main [!] is 📦 v0.1.0 via 🐍 v3.12.8 on ☁️  (us-west-2) on ☁️  mofoster took 59s
❯
```
