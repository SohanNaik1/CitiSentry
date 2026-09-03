# Project CitiSentry: Master Architectural & Operational Specification

**Smart India Hackathon Problem Statement ID:** SIH26127  
**Nodal Organization:** Bharat Electronics Limited (BEL)  
**System Classification:** Tactical Multi-Camera ANPR Trajectory Engine & Command Center (C2)  
**System Topology:** Distributed Edge-to-Core Microservices Ecosystem  

---

## 1. Executive Summary & Operational Mandate

### 1.1 The Operational Challenge
In modern defense, border surveillance, homeland security, and urban traffic monitoring, surveillance operators face a fundamental vulnerability: the inability to reliably track suspect and high-interest vehicles across fragmented, multi-camera city grids.

Conventional Automatic Number Plate Recognition (ANPR) systems fail consistently under real-world operating conditions due to three critical vulnerabilities:

1. **Plate Occlusion and Physical Obscuration:** In dense traffic, adverse weather (fog, heavy rain), night-time glare, oblique camera perspectives, or deliberate physical tampering (mud, tape, tinted plates, or complete removal), license plates become unreadable. Conventional ANPR systems drop tracking immediately, losing the vehicle permanently.
2. **Plate Cloning and Counterfeiting:** Criminal organizations and hostile actors frequently mount counterfeit, stolen, or duplicated number plates onto different vehicles. Traditional systems blindly trust the alphanumeric string, sending interception teams to false locations while the actual target travels undetected.
3. **Multi-Camera Discontinuity (The Inter-Camera Gap):** When a target vehicle exits the visual cone of Camera A and reappears minutes later at Camera B, existing platforms cannot connect the two observations unless a clean, identical license plate is captured at both locations. In dense urban networks with visual blind spots, persistent chain-of-custody tracking is completely broken.

### 1.2 The CitiSentry Operational Solution
CitiSentry is a defense-grade, multi-camera vehicle trajectory engine and tactical command console engineered to deliver continuous, unbroken chain-of-custody tracking across vast urban surveillance matrices.

Even in scenarios where a vehicle has no readable license plate, CitiSentry maintains positive target identification by extracting deep visual appearance embeddings using next-generation convolutional neural networks. It tracks vehicles through dense occlusions using dual-stage association filters, mathematically audits movement feasibility between camera nodes using great-circle road kinematics, and renders real-time pursuit trajectories and velocity vectors on an interactive tactical command console.

---

## 2. Distributed System Architecture & Microservice Topology

CitiSentry is structured as a decoupled, resilient, three-tier microservice architecture designed for high-throughput edge processing, centralized event mediation, and low-latency tactical visualization.

### 2.1 The Three Core Microservices

#### Tier 1: Edge Vision Node
The Edge Vision service serves as the sensory processing core. Deployed at the camera interface or edge computing gateway, it ingests high-definition video feeds, executes deep neural detection, associates multi-object trajectories, extracts appearance embeddings, analyzes color spectra, estimates physical speed, and dispatches standardized telemetry payloads to the central broker. It concurrently serves low-latency video streams to authorized operators.

#### Tier 2: Core Event Broker
The Core Broker operates as the high-concurrency event nexus of the system. Built using idiomatic concurrent systems programming, it receives incoming telemetry payloads from all edge nodes over high-throughput HTTP interfaces. It maintains a thread-safe in-memory event repository, correlates incoming detections against spatial grid topologies, computes physical travel feasibility to detect cloned plate anomalies, and broadcasts enriched telemetry and critical alerts to client consoles via persistent WebSocket connections.

#### Tier 3: Tactical Command & Control (C2) Console
The Tactical Command Console provides mission operators with an integrated situational awareness dashboard. It ingests the live WebSocket stream to update a geographic information system (GIS) tactical map, plots dynamic multi-camera pursuit vectors, draws bounding boxes and telemetry tags directly onto live camera video overlays using accelerated canvas graphics, and provides operators with interactive tools to lock onto targets, switch camera perspectives, and inspect vehicle profiles.

### 2.2 Network Ports and Communication Infrastructure
- **Core Event Broker:** Operates on Port 8080, providing HTTP ingestion endpoints for edge devices and WebSocket upgrade endpoints for operator dashboards.
- **Edge Vision Node:** Operates on Port 5000, providing cross-origin REST control endpoints for camera switching and target locking, alongside raw streaming video channels.
- **Tactical Command Console:** Operates on Port 3000, serving the responsive web-based command console to client workstations.

---

## 3. Edge Computer Vision & Deep Learning Intelligence

The Edge Vision system integrates multiple specialized neural networks and deterministic algorithms into a unified, high-performance processing pipeline.

### 3.1 Object Detection: Ultralytics YOLO11 Extra-Large Architecture
The primary detector utilizes the YOLO11 Extra-Large model, representing the state of the art in real-time object localization.
- **Architectural Advances:** Incorporates optimized C3k2 convolutional feature blocks, Spatial Pyramid Pooling - Fast (SPPF) modules, and an anchor-free detection head. These architectural features enable the model to isolate vehicle boundaries even when vehicles are severely occluded, viewed at steep angles, or partially cropped at frame edges.
- **Target Class Filtering:** Ingestion streams are filtered to isolate transportation targets: Sedans, Motorcycles, Buses, and Trucks, with standard passenger vehicles mapped to broader vehicle categories. Non-vehicular background clutter is discarded prior to downstream analysis.
- **Sensitivity Thresholding:** The detection confidence threshold is calibrated to 0.25. This allows the system to identify vehicles as soon as they emerge from the distant visual horizon, passing candidate regions to the tracking module before traditional filters would discard them.

### 3.2 Multi-Object Tracking: ByteTrack Association
To track multiple vehicles simultaneously without trajectory fragmentation, the vision node utilizes the ByteTrack tracking algorithm.
- **Two-Stage Kalman Association Strategy:** Unlike traditional tracking algorithms that discard any detection with a confidence score below a strict threshold (such as 0.5), ByteTrack divides detections into high-confidence and low-confidence tiers.
  - In the first association stage, high-confidence detections are matched against existing Kalman filter trajectory predictions using Intersection-over-Union distance matrices.
  - In the second association stage, unmatched tracks are compared against the remaining low-confidence detections. This allows the tracker to maintain lock on a vehicle even when it passes behind trees, light poles, or large transport vehicles, eliminating the identity-switching bugs common in dense traffic.

### 3.3 Deep Visual Re-Identification: ConvNeXt-Large Appearance Embeddings
When a vehicle travels between non-overlapping cameras, passes through visual blind spots, or reappears in a looping surveillance sector, spatial trackers inevitably lose track continuity. CitiSentry solves this through deep visual re-identification.
- **Neural Backbone:** The re-identification engine utilizes the ConvNeXt-Large deep convolutional architecture, pre-trained on extensive visual datasets.
- **Feature Extraction Head:** The final linear classification layer is excised and replaced with an identity passthrough, enabling direct extraction of raw convolutional feature representations.
- **Embedding Dimensionality:** The network projects the cropped vehicle image into a dense, 1536-dimensional appearance vector. This vector captures micro-features of the vehicle that remain invariant across viewpoints: body aspect ratios, window geometry, grill structure, wheel rim designs, and distinct surface markings.
- **Mathematical Normalization and Matching:** Every extracted embedding is normalized using Euclidean L2 norm scaling so that its magnitude equals one. The vision node maintains an in-memory gallery of locked target profiles. When a candidate vehicle is tracked, its appearance vector is compared against existing profiles using Cosine Similarity, which evaluates the angular distance between the two high-dimensional vectors.
- **Re-Identification Threshold:** If the cosine similarity between the current detection and an existing profile meets or exceeds 0.85, the system mathematically confirms that the detected vehicle is the identical physical target. It binds the target to the existing persistent profile identifier (formatted as TRK followed by a unique hexadecimal tag), flags the target as re-identified, and preserves tracking continuity without generating duplicate records.

### 3.4 License Plate Recognition & Anti-Branding Filtering
- **Optical Character Recognition:** Automatic Number Plate Recognition is driven by an EasyOCR character recognition pipeline.
- **Image Pre-Processing:** To read plates in degraded conditions, the vehicle crop is isolated to its lower vertical section (the bumper and trunk area), converted to grayscale, and upscaled by two hundred percent using bicubic interpolation. This sharpens alphanumeric character boundaries before character segmentation.
- **Commercial Logo and Delivery Branding Suppression:** Commercial logistics and delivery vans frequently display prominent branding text (such as FedEx, Amazon, or DHL) on their cargo bodies, causing naive OCR systems to register company names as license plates. CitiSentry implements negative-lookahead regular expression filtering that rejects delivery fleet keywords and strictly enforces alphanumeric syntax rules between four and ten characters with high confidence scores.

### 3.5 Dominant Color Extraction via HSV Spectral Masking
Vehicle color classification must remain robust despite changing ambient sunlight, streetlamp color temperatures, and cloud cover. The vision pipeline resizes vehicle crops to a standardized thumbnail and converts the color space from RGB to Hue-Saturation-Value (HSV).
- The thumbnail is evaluated across six calibrated spectral bands: White, Black, Silver, Red, Blue, and Yellow.
- To handle the circular nature of the hue spectrum, Red color classification utilizes a dual-boundary wraparound mask that captures hue angles at both the extreme beginning and end of the hue circle.
- The color band with the highest pixel count is assigned as the dominant vehicle color, providing an auxiliary visual search filter.

### 3.6 Windowed Bottom-Center Velocity Estimation
Conventional vision systems estimate velocity by calculating the displacement of bounding box centroids between consecutive frames. However, as vehicles turn, accelerate, or change visual perspective, bounding box dimensions stretch and contract unevenly, causing centroid jitter that produces erratic speed spikes or false zero readings.

CitiSentry implements Windowed Displacement on Bottom-Center Coordinates:
1. **Ground-Contact Coordinate Anchoring:** The tracking anchor is positioned at the bottom-center of the bounding box, representing the physical point where the vehicle's tires contact the road surface. This eliminates vertical height distortion caused by perspective scaling.
2. **Rolling Temporal Window:** Coordinates and capture timestamps are maintained in a rolling fifteen-frame historical queue.
3. **Displacement Derivation:** Velocity is computed over the full fifteen-frame temporal window rather than between single frames. Pixel displacement is divided by a calibrated perspective scale factor (fifteen pixels per physical meter) and divided by elapsed time, yielding physical velocity in kilometers per hour.
4. **Exponential Smoothing Filter:** An exponential moving average filter is applied to eliminate sudden noise while permitting smooth, natural acceleration and deceleration profiles. Calculated velocities are clamped within realistic bounds of zero to one hundred twenty kilometers per hour.

### 3.7 Global DVR Timeline Synchronization
During multi-camera operations, recorded surveillance streams from disparate sensors can easily drift out of temporal alignment if replayed independently.
- CitiSentry establishes a global master reference clock at system initialization.
- When an operator switches from one camera feed to another, the vision engine calculates the modulo elapsed time against the target video's total duration and automatically seeks the video stream to the exact chronological millisecond. This ensures that vehicles moving through an intersection are observed in perfect temporal correlation across all camera angles.

---

## 4. Core Event Broker & Spatiotemporal Anomaly Engine

The Core Broker is designed for mission-critical reliability, thread safety, and millisecond-level event mediation.

### 4.1 In-Memory Concurrent Telemetry Store
The broker maintains an internal, thread-safe telemetry repository protected by reader-writer mutual exclusion locks. Multiple ingestion goroutines can read and update camera statuses concurrently without lock contention. In addition to chronological event storage, the repository maintains an indexed lookup table keyed by license plate text and persistent profile identifier, allowing instantaneous historical retrieval of any target's previous sighting.

### 4.2 Spatiotemporal Kinematic Anomaly Engine (Anti-Spoofing)
The primary intelligence feature of the broker is its automated physical anomaly engine, which mathematically validates vehicle trajectories against real-world road kinematics.

#### The Kinematic Auditing Process:
1. When a telemetry event for a vehicle is ingested at Camera B at a specific timestamp, the engine queries the store for the vehicle's most recent prior detection, which occurred at Camera A at an earlier timestamp.
2. If both detections originate from the same camera, the event represents continuous dwell time and is marked normal.
3. If the detections originate from two different camera nodes, the engine retrieves the geographic coordinates (latitude and longitude) of both installations from the spatial registry.
4. It computes the physical Great-Circle distance between the two points across the Earth's surface using the Haversine trigonometric formulation:
   - The differences in latitude and longitude are converted to radians.
   - The spherical angular separation is derived using half-angle sine squares and cosine products.
   - The angular separation is multiplied by the mean radius of the Earth (six thousand three hundred seventy-one kilometers) to determine the exact physical distance in kilometers.
5. The elapsed time between the two events is calculated in hours by subtracting the earlier millisecond timestamp from the later timestamp.
6. The required travel velocity is derived by dividing physical distance by elapsed time.

#### Kinematic Rule Enforcement:
- **Maximum Feasible Physical Speed Threshold:** Calibrated to two hundred fifty kilometers per hour, representing the absolute upper limit of road travel.
- **Physical Feasibility Check:**
  - If the derived travel speed exceeds two hundred fifty kilometers per hour, or if the time delta is zero or negative (indicating simultaneous detection at two distant physical locations), the system identifies an undeniable violation of physical laws.
  - The engine immediately constructs a Critical Alert Event with the classification of Cloned Plate Spoof.
  - The alert details the exact locations, distance traveled, elapsed time, and required impossible speed.
  - The alert is pushed through the WebSocket broadcasting channel to all active command consoles in less than two milliseconds, alerting operators to interdict the duplicate vehicle.

### 4.3 Spatial Topology Registry
The spatial registry maintains an in-memory graph of camera nodes loaded from canonical topology configurations. It manages thirty geographic camera installations:
- **Bangalore Urban Security Corridors:** Encompasses key strategic traffic junctions including MG Road Junction, Indiranagar 100ft Road, Koramangala Sony World Signal, Silk Board Junction, and Brigade Road Entrance.
- **Iowa Highway Grid Intersections:** Encompasses twenty-five high-density multi-lane intersection cameras (CAM-016 through CAM-040) calibrated with synchronized video channels for multi-target multi-camera tracking validation.

---

## 5. Tactical Command & Control (C2) Frontend Console

The user interface is an operational command console designed specifically for surveillance operators, defense analysts, and incident commanders.

### 5.1 Tactical Dark Theme Visual Hierarchy
The interface adheres strictly to defense-grade ergonomic standards designed to minimize operator fatigue during extended monitoring shifts:
- **Foundational Backgrounds:** Deep matte blacks, charcoal, and slate gray tones provide high contrast without visual glare.
- **Tactical Status Accents:**
  - **Emerald Online:** Signifies active camera sensors, verified normal tracking, and nominal travel velocities.
  - **Amber Suspect:** Highlights degraded camera streams, ambiguous OCR readings, and minor speed variations.
  - **Crimson Alert:** Designates critical spatiotemporal violations, cloned plates, stolen vehicle hotlist hits, and trajectory anomalies.
  - **Cyan Telemetry:** Identifies real-time spatial polyline vectors, heading vectors, active profile IDs, and monospaced telemetry telemetry logs.
- **Typography:** Monospaced fonts are enforced across all telemetry fields, geographic coordinates, timestamps, and plate identifiers to prevent visual misalignment during high-speed data updates.

### 5.2 Key Operational Modules

#### Interactive GIS Tactical Map
Constructed on top of a Leaflet geographic mapping engine, the map display is styled with custom dark-matter cartographic tiles.
- Displays all registered camera nodes with status indicator rings.
- Clicking any camera node instantly directs the edge vision node to switch its active stream to that camera's video source.
- When an active target is tracked across multiple cameras, the map dynamically renders a glowing cyan polyline connecting the sequence of cameras where the vehicle was sighted, plotting its verified pursuit trajectory across the city grid.

#### Video Viewport & Dynamic Canvas Overlay
The video panel displays the incoming MJPEG video stream from the active camera node.
- An HTML5 Canvas layer is mounted directly above the video stream.
- Ingestion telemetry provides normalized bounding box coordinates ranging from zero to one. The canvas dynamically projects these fractional coordinates into exact screen pixel dimensions matching the operator's display resolution.
- A glowing tactical reticle, tracking tag, and velocity readout are drawn directly over the vehicle in real time.
- Operators can click on any vehicle or drag a tactical Region of Interest (ROI) box directly over the stream to command the edge node to acquire lock on that target.

#### State Management & Profile Deduplication
The frontend uses the Zustand global state store. To eliminate a common flaw in surveillance dashboards where events with unknown or missing plates overwrite one another in the telemetry log, CitiSentry indexes all telemetry events by their persistent profile identifier (the system ID). This ensures that every individual vehicle maintains its own persistent history card in the operational feed, allowing operators to monitor multiple unplated vehicles concurrently.

---

## 6. Canonical Data Contracts & Information Schemas

All services communicate through standardized, strictly typed data structures.

### 6.1 Telemetry Event Data Contract
Every detection frame dispatched by an edge camera generates a Telemetry Event containing the following structured data:
- **Event Identifier:** A globally unique UUID identifying the single observation frame.
- **System Identifier:** A persistent profile tag (e.g., TRK-194B) assigned to the vehicle across multiple observations and re-identification matches.
- **Camera Identifier:** The unique alphanumeric code of the reporting camera node.
- **Timestamp:** ISO-8601 formatted UTC timestamp of detection.
- **Epoch Milliseconds:** Integer millisecond timestamp used for high-precision kinematic delta calculations.
- **License Plate Object:**
  - Text string of the recognized plate, or "UNKNOWN" if occluded or missing.
  - Confidence score representing character recognition certainty.
  - Clean plate flag indicating whether the detection was confirmed via deep visual re-identification.
- **Bounding Box Array:** Four floating-point coordinates representing normalized minimum x, minimum y, maximum x, and maximum y boundaries within the frame.
- **Vehicle Attributes Object:**
  - Classified vehicle type (Sedan, SUV, Bus, Truck, Motorcycle).
  - Classified dominant color (White, Black, Silver, Red, Blue, Yellow).
  - Confidence rating for color classification.
- **Speed Estimate:** Calibrated vehicle travel velocity in kilometers per hour.
- **Heading Degrees:** Directional orientation in angular degrees.
- **Re-Identification Embeddings:** Serialized array containing the primary dimensions of the normalized appearance vector.
- **Video Time Seconds:** Relative playback timestamp within the active video stream.

### 6.2 Alert Event Data Contract
When the anomaly engine detects a rule violation or cloned vehicle, it generates an Alert Event containing:
- **Alert Identifier:** A globally unique UUID identifying the violation.
- **Alert Type:** Categorical violation type, such as Cloned Plate Spoof, Hotlist Hit, Speed Violation, or Blind Spot Deviation.
- **Severity Rating:** Operational priority level: Critical, High, Medium, or Information.
- **Target Plate:** The license plate text associated with the violation.
- **Source Camera Identifier:** The camera node that detected the violating event.
- **Details:** Comprehensive textual narrative explaining the exact physical impossibility, including prior camera, current camera, physical distance in kilometers, elapsed time in milliseconds, and derived velocity.
- **Creation Timestamp:** ISO-8601 formatted UTC timestamp when the alert was triggered.

### 6.3 Camera Node Data Contract
Each camera in the surveillance network is defined by:
- **Camera Identifier:** Unique alphanumeric identifier (e.g., CAM-001).
- **Descriptive Name:** Human-readable geographic location name (e.g., MG Road Junction).
- **Latitude and Longitude:** Precise geographic coordinates in decimal degrees.
- **Operational Status:** Current operational health: Online, Offline, or Degraded.
- **Stream URL:** RTSP or HTTP network endpoint for video ingestion.
- **Frame Rate:** Operating capture frequency in frames per second.
- **Video Source File:** Relative path to local video archives used for simulated playback.

---

## 7. Operational Deployment Configurations & Hardware Tiers

CitiSentry is architected to scale seamlessly across different hardware deployment environments without code modifications.

### 7.1 Field Inspection Node
- **Deployment Scenario:** Portable checkpoints, mobile border posts, temporary security barriers.
- **Target Hardware:** Standard field computing terminals with multi-core x86 processors and sixteen gigabytes of system memory.
- **Model Configuration:** Standard quantized neural backbones for detection and appearance extraction.
- **Operating Performance:** Delivers real-time processing across one to two localized camera channels with full re-identification capabilities.

### 7.2 Tactical Mobile Command Unit
- **Deployment Scenario:** Mobile surveillance vans, rapid-deployment tactical response vehicles, regional headquarters.
- **Target Hardware:** High-performance workstations equipped with dedicated graphics acceleration processors.
- **Model Configuration:** Full-precision YOLO11 Extra-Large detection coupled with ConvNeXt-Large deep re-identification.
- **Operating Performance:** Delivers high frame-rate processing across multiple concurrent high-definition camera feeds with sub-millisecond feature extraction.

### 7.3 Enterprise Central Surveillance Grid
- **Deployment Scenario:** State-level police headquarters, national highway surveillance command centers, defense monitoring installations.
- **Target Hardware:** Enterprise server clusters equipped with multi-GPU tensor compute arrays and redundant network interfaces.
- **Model Configuration:** TensorRT-compiled detection pipelines with batched GPU re-identification galleries.
- **Operating Performance:** Supports hundreds of distributed camera channels simultaneously, maintaining persistent trajectory histories across entire metropolitan regions.

---

## 8. System Startup & Operational Lifecycle

The system incorporates automated process management to ensure dependable startup, clean teardown, and conflict-free port binding across operating systems.

### 8.1 Automated Service Boot Sequence
1. **Pre-Flight Port Verification:** The startup system audits required network ports (3000, 5000, and 8080) and automatically terminates any lingering background processes from previous sessions, guaranteeing that socket collisions cannot occur.
2. **Core Broker Arming:** The Go Core Broker is initiated first. The system pauses for two seconds to permit the in-memory database and spatial topology registry to load completely and bind Port 8080.
3. **Edge Vision Initialization:** The Python Edge Vision node is launched. It loads model weights, verifies video stream accessibility, synchronizes the global DVR clock, and begins background inference.
4. **Command Console Launch:** The Next.js web application is launched on Port 3000, connecting its WebSocket client to the armed Core Broker.
5. **Graceful Shutdown Management:** When the operator initiates system shutdown, signal traps intercept the termination request and simultaneously close all three child processes, leaving the host system clean.

### 8.2 End-to-End Operational Workflow
1. **Operator Access:** The operator opens the command console in any modern web browser.
2. **Camera Selection:** The operator selects an active camera from the tactical map or camera control buttons. The vision engine immediately streams live video.
3. **Target Locking:** The operator identifies a suspect vehicle on screen and clicks it, or drags a rectangular Region of Interest over it.
4. **Telemetry Generation:** The vision engine locks the tracking reticle onto the vehicle, extracts its ConvNeXt-Large appearance vector, records its color and speed, and transmits telemetry to the broker.
5. **Real-Time Verification:** The operator observes live speed readouts and HUD overlays.
6. **Multi-Camera Hand-off:** The operator switches to downstream camera feeds along the suspect's expected route. When the vehicle enters the new frame, the re-identification engine recognizes the appearance embedding and automatically resumes tracking under the same profile identifier.
7. **Anomaly Detection:** If a counterfeit vehicle displaying the same license plate appears simultaneously or too quickly at another sensor, the broker triggers a Critical Alert, displaying a flashing banner on the operator's console with full kinematic violation details.

---
*CitiSentry represents an advanced technological implementation for defense and homeland security mobility intelligence, fulfilling all operational requirements specified under Smart India Hackathon Problem Statement SIH26127.*
