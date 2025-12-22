# ApiKeyRouter Product Flow

This document provides a comprehensive flowchart explaining how ApiKeyRouter processes requests from start to finish.

## Main Request Flow

```mermaid
flowchart TD
    Start([Application Makes Request]) --> Init{Request Intent Valid?}
    Init -->|No| Error1[Return ValueError]
    Init -->|Yes| LogStart[Log Request Start<br/>Generate request_id & correlation_id]
    
    LogStart --> GetObjective{Objective Provided?}
    GetObjective -->|No| DefaultObj[Use Default: Fairness]
    GetObjective -->|Yes| UseObj[Use Provided Objective]
    DefaultObj --> RouteEngine
    UseObj --> RouteEngine
    
    RouteEngine[RoutingEngine.route_request] --> GetEligible[Get Eligible Keys from KeyManager]
    GetEligible --> CheckQuota[For Each Key:<br/>Check Quota State via QuotaAwarenessEngine]
    CheckQuota --> EstimateCost[For Each Key:<br/>Estimate Cost via CostController]
    EstimateCost --> CheckBudget[For Each Key:<br/>Check Budget Constraints]
    CheckBudget --> Evaluate[Evaluate Keys Based on:<br/>- Objective cost/reliability/fairness<br/>- Quota state<br/>- Cost estimates<br/>- Policy constraints]
    
    Evaluate --> SelectKey{Keys Available?}
    SelectKey -->|No| NoKeys[Raise NoEligibleKeysError]
    SelectKey -->|Yes| BestKey[Select Best Key<br/>Generate Explanation]
    
    BestKey --> SaveDecision[Save Routing Decision to StateStore]
    SaveDecision --> LogDecision[Log Routing Decision]
    LogDecision --> GetAdapter[Get ProviderAdapter for Provider]
    
    GetAdapter --> Execute[Execute Request via Adapter]
    Execute --> CheckSuccess{Request Successful?}
    
    CheckSuccess -->|Yes| UpdateQuota[Update Quota State<br/>Record Token Usage]
    UpdateQuota --> UpdateStats[Update Key Usage Statistics]
    UpdateStats --> LogSuccess[Log Successful Completion]
    LogSuccess --> ReturnSuccess[Return SystemResponse]
    
    CheckSuccess -->|No| InterpretError[Interpret Error via FailureHandler]
    InterpretError --> UpdateKeyState[Update Key State<br/>Throttled/Exhausted/etc]
    UpdateKeyState --> CheckRetry{Retryable Error?}
    
    CheckRetry -->|No| LogFailure[Log Failure]
    LogFailure --> ReturnError[Return SystemError]
    
    CheckRetry -->|Yes| CheckAttempts{Attempts < Max?}
    CheckAttempts -->|No| LogFailure
    CheckAttempts -->|Yes| GetAltKey[Get Alternative Key<br/>Exclude Tried Keys]
    GetAltKey --> CheckAltKey{Alternative Key Available?}
    CheckAltKey -->|No| LogFailure
    CheckAltKey -->|Yes| Execute
    
    style Start fill:#e1f5ff
    style ReturnSuccess fill:#c8e6c9
    style ReturnError fill:#ffcdd2
    style NoKeys fill:#ffcdd2
    style Error1 fill:#ffcdd2
```

## Key Registration Flow

```mermaid
flowchart TD
    Start([Register Key Request]) --> ValidateProvider{Provider Registered?}
    ValidateProvider -->|No| Error1[Return ValueError:<br/>Provider not registered]
    ValidateProvider -->|Yes| Encrypt[KeyManager:<br/>Encrypt Key Material]
    
    Encrypt --> GenerateID[Generate Unique Key ID]
    GenerateID --> CreateKey[Create APIKey Object<br/>State: Available]
    CreateKey --> SaveKey[Save to StateStore]
    SaveKey --> LogTransition[Log State Transition<br/>None → Available]
    LogTransition --> EmitEvent[Emit Key Registered Event]
    EmitEvent --> InitQuota[Initialize QuotaState<br/>via QuotaAwarenessEngine]
    InitQuota --> LogSuccess[Log Key Registration Success]
    LogSuccess --> ReturnKey[Return APIKey Object]
    
    style Start fill:#e1f5ff
    style ReturnKey fill:#c8e6c9
    style Error1 fill:#ffcdd2
```

## Provider Registration Flow

```mermaid
flowchart TD
    Start([Register Provider Request]) --> ValidateID{Provider ID Valid?}
    ValidateID -->|No| Error1[Return ValueError]
    ValidateID -->|Yes| ValidateAdapter{Adapter Valid?}
    
    ValidateAdapter -->|No| Error2[Return ValueError/TypeError]
    ValidateAdapter -->|Yes| CheckMethods{All Required Methods Present?}
    CheckMethods -->|No| Error3[Return TypeError]
    CheckMethods -->|Yes| CheckDuplicate{Provider Already Exists?}
    
    CheckDuplicate -->|Yes & No Overwrite| Error4[Return ValueError:<br/>Provider already registered]
    CheckDuplicate -->|Yes & Overwrite| StoreProvider
    CheckDuplicate -->|No| StoreProvider[Store Provider-Adapter Mapping]
    
    StoreProvider --> LogRegistration[Log Provider Registration]
    LogRegistration --> EmitEvent[Emit Provider Registered Event]
    EmitEvent --> Success[Registration Complete]
    
    style Start fill:#e1f5ff
    style Success fill:#c8e6c9
    style Error1 fill:#ffcdd2
    style Error2 fill:#ffcdd2
    style Error3 fill:#ffcdd2
    style Error4 fill:#ffcdd2
```

## Routing Decision Flow (Detailed)

```mermaid
flowchart TD
    Start([RoutingEngine.route_request]) --> GetPolicy[Get Applicable Policies<br/>via PolicyEngine]
    GetPolicy --> GetKeys[Get Eligible Keys<br/>via KeyManager]
    GetKeys --> FilterKeys{Keys Found?}
    
    FilterKeys -->|No| NoKeys[Raise NoEligibleKeysError]
    FilterKeys -->|Yes| LoopStart[For Each Eligible Key]
    
    LoopStart --> GetQuota[Get Quota State<br/>via QuotaAwarenessEngine]
    GetQuota --> PredictExhaustion{Predict Exhaustion?}
    PredictExhaustion -->|Yes| CalcExhaustion[Calculate Exhaustion Time<br/>Based on Usage Rate]
    PredictExhaustion -->|No| SkipPrediction
    CalcExhaustion --> SkipPrediction[Continue Evaluation]
    
    SkipPrediction --> EstimateCost[Estimate Request Cost<br/>via CostController]
    EstimateCost --> CheckBudget[Check Budget Constraints]
    CheckBudget --> ScoreKey[Score Key Based on:<br/>- Objective weights<br/>- Quota state<br/>- Cost estimate<br/>- Policy constraints]
    
    ScoreKey --> NextKey{More Keys?}
    NextKey -->|Yes| LoopStart
    NextKey -->|No| RankKeys[Rank Keys by Score]
    
    RankKeys --> ApplyPolicy[Apply Policy Filters<br/>Remove Keys Violating Policies]
    ApplyPolicy --> SelectBest[Select Best Key<br/>Highest Score]
    SelectBest --> GenerateExplanation[Generate Explanation:<br/>Why this key was chosen]
    GenerateExplanation --> ReturnDecision[Return RoutingDecision]
    
    style Start fill:#e1f5ff
    style ReturnDecision fill:#c8e6c9
    style NoKeys fill:#ffcdd2
```

## Error Handling & Retry Flow

```mermaid
flowchart TD
    Start([Request Execution Failed]) --> ClassifyError[FailureHandler:<br/>Classify Error Type]
    ClassifyError --> ErrorType{Error Category?}
    
    ErrorType -->|Rate Limit 429| RateLimit[Extract Retry-After<br/>Set Cooldown Period]
    ErrorType -->|Quota Exhausted| QuotaExhausted[Mark Key as Exhausted]
    ErrorType -->|Authentication Error| AuthError[Mark Key as Invalid]
    ErrorType -->|Provider Error| ProviderError[Mark Key as Throttled]
    ErrorType -->|Network Error| NetworkError[Mark as Temporary Failure]
    
    RateLimit --> UpdateState1[Update Key State to Throttled]
    QuotaExhausted --> UpdateState2[Update Quota State to Exhausted]
    AuthError --> UpdateState3[Update Key State to Disabled]
    ProviderError --> UpdateState4[Update Key State to Throttled]
    NetworkError --> UpdateState5[Keep Key Available<br/>Mark for Retry]
    
    UpdateState1 --> CheckRetry
    UpdateState2 --> CheckRetry
    UpdateState3 --> CheckRetry
    UpdateState4 --> CheckRetry
    UpdateState5 --> CheckRetry
    
    CheckRetry{Error Retryable?}
    CheckRetry -->|No| LogFailure[Log Failure<br/>Return Error]
    CheckRetry -->|Yes| CheckAttempts{Attempts < Max?}
    
    CheckAttempts -->|No| LogFailure
    CheckAttempts -->|Yes| GetAltKey[Get Alternative Key<br/>Exclude Failed Keys]
    GetAltKey --> CheckAlt{Alternative Available?}
    CheckAlt -->|No| LogFailure
    CheckAlt -->|Yes| RetryRequest[Retry Request<br/>with New Key]
    RetryRequest --> CheckSuccess{Success?}
    
    CheckSuccess -->|Yes| LogRetrySuccess[Log Retry Success]
    CheckSuccess -->|No| CheckAttempts
    
    style Start fill:#e1f5ff
    style LogRetrySuccess fill:#c8e6c9
    style LogFailure fill:#ffcdd2
```

## Quota Awareness Flow

```mermaid
flowchart TD
    Start([Quota State Check]) --> GetState[Get Current Quota State<br/>from StateStore]
    GetState --> StateExists{State Exists?}
    
    StateExists -->|No| Initialize[Initialize New QuotaState<br/>State: Abundant]
    StateExists -->|Yes| CheckState{Current State?}
    
    Initialize --> ReturnState
    CheckState -->|Abundant| CheckUsage[Check Usage Rate]
    CheckState -->|Constrained| CheckUsage
    CheckState -->|Critical| CheckUsage
    CheckState -->|Exhausted| ReturnExhausted
    
    CheckUsage --> CalcRate[Calculate Usage Rate<br/>requests/hour or tokens/hour]
    CalcRate --> CalcRemaining[Calculate Remaining Capacity]
    CalcRemaining --> PredictTime[Predict Exhaustion Time<br/>remaining / rate]
    
    PredictTime --> EvaluateState{Exhaustion < Threshold?}
    EvaluateState -->|Yes & < 4 hours| SetCritical[Set State to Critical<br/>Save Prediction]
    EvaluateState -->|Yes & < 1 hour| SetExhausted[Set State to Exhausted]
    EvaluateState -->|No| KeepState[Keep Current State]
    
    SetCritical --> ReturnState
    SetExhausted --> ReturnExhausted
    KeepState --> ReturnState
    
    ReturnState[Return QuotaState<br/>with Prediction]
    ReturnExhausted[Return QuotaState<br/>State: Exhausted]
    
    style Start fill:#e1f5ff
    style ReturnState fill:#c8e6c9
    style ReturnExhausted fill:#ffcdd2
```

## Cost Estimation & Budget Flow

```mermaid
flowchart TD
    Start([Estimate Request Cost]) --> GetModel[Get Cost Model<br/>for Provider]
    GetModel --> EstimateTokens[Estimate Token Count<br/>Input + Output]
    EstimateTokens --> CalcCost[Calculate Cost:<br/>input_tokens × input_price +<br/>output_tokens × output_price]
    CalcCost --> ReturnEstimate[Return Cost Estimate<br/>with Confidence Score]
    
    ReturnEstimate --> CheckBudget[Check Budget Status<br/>from StateStore]
    CheckBudget --> GetBudget[Get Budget for Scope<br/>limit, current, remaining]
    GetBudget --> WouldExceed{Would Exceed Budget?}
    
    WouldExceed -->|Yes| Enforcement{Enforcement Mode?}
    WouldExceed -->|No| AllowRequest[Allow Request<br/>Reserve Budget]
    
    Enforcement -->|Hard| RejectRequest[Reject Request<br/>Return BudgetExceededError]
    Enforcement -->|Soft| Downgrade[Downgrade Request<br/>Use Cheaper Model]
    Downgrade --> ReEstimate[Re-estimate Cost<br/>with Downgraded Model]
    ReEstimate --> CheckBudget
    
    AllowRequest --> Reserve[Reserve Budget Amount]
    Reserve --> ExecuteRequest[Execute Request]
    ExecuteRequest --> RecordActual[Record Actual Cost]
    RecordActual --> Reconcile[Reconcile Estimate vs Actual]
    Reconcile --> UpdateBudget[Update Budget Status]
    
    style Start fill:#e1f5ff
    style AllowRequest fill:#c8e6c9
    style RejectRequest fill:#ffcdd2
```

## State Transition Flow

```mermaid
flowchart TD
    Start([State Change Request]) --> GetCurrent[Get Current State<br/>from StateStore]
    GetCurrent --> ValidateTransition{Transition Valid?}
    
    ValidateTransition -->|No| Error[Return InvalidTransitionError]
    ValidateTransition -->|Yes| UpdateState[Update State in StateStore]
    
    UpdateState --> LogTransition[Log State Transition<br/>with Reason & Timestamp]
    LogTransition --> EmitEvent[Emit State Changed Event]
    EmitEvent --> UpdateObservability[Update Observability Metrics]
    
    UpdateObservability --> CheckRecovery{State Requires<br/>Recovery Monitoring?}
    CheckRecovery -->|Yes| StartMonitoring[Start Background<br/>Recovery Monitoring]
    CheckRecovery -->|No| Complete
    
    StartMonitoring --> HealthCheck[Periodic Health Checks]
    HealthCheck --> CheckHealthy{Key Healthy?}
    CheckHealthy -->|Yes| TransitionRecovered[Transition to Available]
    CheckHealthy -->|No| ContinueMonitoring[Continue Monitoring]
    ContinueMonitoring --> HealthCheck
    
    TransitionRecovered --> Complete[State Transition Complete]
    
    style Start fill:#e1f5ff
    style Complete fill:#c8e6c9
    style Error fill:#ffcdd2
```

## Component Interaction Overview

```mermaid
graph TB
    subgraph "Application Layer"
        APP[Application Code]
    end
    
    subgraph "ApiKeyRouter (Orchestrator)"
        ROUTER[ApiKeyRouter]
    end
    
    subgraph "Core Components"
        KM[KeyManager<br/>Key Lifecycle & State]
        RE[RoutingEngine<br/>Intelligent Selection]
        QA[QuotaAwarenessEngine<br/>Capacity Prediction]
        CC[CostController<br/>Budget Management]
        PE[PolicyEngine<br/>Policy Evaluation]
        FH[FailureHandler<br/>Error Interpretation]
    end
    
    subgraph "Infrastructure"
        SS[StateStore<br/>Persistence Layer]
        OM[ObservabilityManager<br/>Logging & Metrics]
        ADAPTER[ProviderAdapter<br/>Provider Abstraction]
    end
    
    subgraph "External"
        PROVIDER[External Provider API]
    end
    
    APP -->|route| ROUTER
    ROUTER -->|orchestrates| KM
    ROUTER -->|orchestrates| RE
    ROUTER -->|orchestrates| QA
    ROUTER -->|orchestrates| CC
    ROUTER -->|orchestrates| PE
    ROUTER -->|orchestrates| FH
    
    RE -->|queries| KM
    RE -->|queries| QA
    RE -->|queries| CC
    RE -->|queries| PE
    
    KM -->|stores| SS
    QA -->|stores| SS
    CC -->|stores| SS
    RE -->|stores| SS
    
    KM -->|logs| OM
    QA -->|logs| OM
    RE -->|logs| OM
    CC -->|logs| OM
    
    ROUTER -->|executes| ADAPTER
    ADAPTER -->|calls| PROVIDER
    
    style ROUTER fill:#e1f5ff
    style KM fill:#fff4e1
    style RE fill:#fff4e1
    style QA fill:#fff4e1
    style CC fill:#fff4e1
    style PE fill:#fff4e1
    style FH fill:#fff4e1
```

## Key Decision Points

1. **Routing Decision**: Based on objective (cost/reliability/fairness), quota state, cost estimates, and policies
2. **Error Handling**: Semantic error interpretation determines retry strategy
3. **Quota Prediction**: Forward-looking capacity analysis prevents routing to exhausted keys
4. **Budget Enforcement**: Cost estimation before execution with hard/soft enforcement modes
5. **State Transitions**: Explicit state management with validation and audit trails
6. **Retry Logic**: Intelligent retries with different keys, not blind retries

## Flow Characteristics

- **Async/Await**: All I/O operations are asynchronous
- **Graceful Degradation**: System continues operating with remaining keys when some fail
- **Observability**: All decisions and state changes are logged
- **Explainability**: Every routing decision includes an explanation
- **Predictive**: Quota exhaustion predicted before it happens
- **Policy-Driven**: Routing decisions respect configured policies

