import React, { useEffect, useRef, useState } from 'react';
import opticalReefSrc from '../assets/images/underwater_coral_reef_panorama_1794126748001.jpg';
import uvReefSrc from '../assets/images/underwater_uv_fluorescence_reef_1794126747779.jpg';
import {
  CoralCluster,
  ReviewerStatus,
  computeSpectralCurve,
  projectPixelToWorld,
  validatePcaSurfaceNormal,
} from '../domain/reefEngine';
import {
  Camera,
  Eye,
  Crosshair,
  Sparkles,
  Layers,
  Grid,
  ZoomIn,
  ZoomOut,
  RotateCcw,
  RotateCw,
  Box,
  ArrowLeftRight,
  Maximize2,
  Minimize2,
} from 'lucide-react';

const OPTICAL_REEF_SRC = opticalReefSrc;
const UV_REEF_SRC = uvReefSrc;

interface LiveCameraFeedProps {
  clusters: CoralCluster[];
  selectedClusterId: string;
  onSelectCluster: (id: string) => void;
  vehiclePos: [number, number, number];
  turbidity: number;
  currentSpeedMs: number;
  holdingFragment: boolean;
  onUpdateReviewerStatus?: (clusterId: string, status: ReviewerStatus) => void;
  onSwapSlot?: () => void;
  onToggleExpand?: () => void;
  isExpanded?: boolean;
}

interface TrackedBoxScreen {
  id: string;
  cluster: CoralCluster;
  x: number;
  y: number;
  w: number;
  h: number;
  worldX: number;
  worldY: number;
  worldZ: number;
  confidence: number;
}

type SpectralMode = 'optical' | 'fluorescence' | 'depth' | 'normals' | 'quad';

export const LiveCameraFeed: React.FC<LiveCameraFeedProps> = ({
  clusters,
  selectedClusterId,
  onSelectCluster,
  vehiclePos,
  turbidity,
  currentSpeedMs,
  holdingFragment,
  onUpdateReviewerStatus,
  onSwapSlot,
  onToggleExpand,
  isExpanded,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const opticalImgRef = useRef<HTMLImageElement | null>(null);
  const uvImgRef = useRef<HTMLImageElement | null>(null);

  const [showDetections, setShowDetections] = useState(true);
  const [showNormals, setShowNormals] = useState(true);
  const [spectralMode, setSpectralMode] = useState<SpectralMode>('optical');
  const [usingWebcam, setUsingWebcam] = useState(false);
  const [webcamError, setWebcamError] = useState<string | null>(null);
  const [hoveredBoxId, setHoveredBoxId] = useState<string | null>(null);

  // Interactive camera spin/pan/zoom & 3D object turntable state
  const [camZoom, setCamZoom] = useState<number>(1.0);
  const [camPan, setCamPan] = useState<[number, number]>([0, 0]); // normalized [-0.35, 0.35]
  const [objectSpinAngle, setObjectSpinAngle] = useState<number>(0.4);
  const [showTurntableOverlay, setShowTurntableOverlay] = useState<boolean>(true);
  const [isDraggingFeed, setIsDraggingFeed] = useState<boolean>(false);
  const dragStartRef = useRef<{ x: number; y: number; panX: number; panY: number; spin: number }>({
    x: 0,
    y: 0,
    panX: 0,
    panY: 0,
    spin: 0,
  });

  const trackedBoxesRef = useRef<TrackedBoxScreen[]>([]);

  // Preload photorealistic underwater reef frames
  useEffect(() => {
    const optImg = new Image();
    optImg.crossOrigin = 'anonymous';
    optImg.src = OPTICAL_REEF_SRC;
    opticalImgRef.current = optImg;

    const uvImg = new Image();
    uvImg.crossOrigin = 'anonymous';
    uvImg.src = UV_REEF_SRC;
    uvImgRef.current = uvImg;
  }, []);

  const stateRef = useRef({
    clusters,
    selectedClusterId,
    vehiclePos,
    turbidity,
    currentSpeedMs,
    holdingFragment,
    showDetections,
    showNormals,
    spectralMode,
    usingWebcam,
    hoveredBoxId,
    camZoom,
    camPan,
    objectSpinAngle,
    showTurntableOverlay,
  });

  useEffect(() => {
    stateRef.current = {
      clusters,
      selectedClusterId,
      vehiclePos,
      turbidity,
      currentSpeedMs,
      holdingFragment,
      showDetections,
      showNormals,
      spectralMode,
      usingWebcam,
      hoveredBoxId,
      camZoom,
      camPan,
      objectSpinAngle,
      showTurntableOverlay,
    };
  }, [
    clusters,
    selectedClusterId,
    vehiclePos,
    turbidity,
    currentSpeedMs,
    holdingFragment,
    showDetections,
    showNormals,
    spectralMode,
    usingWebcam,
    hoveredBoxId,
    camZoom,
    camPan,
    objectSpinAngle,
    showTurntableOverlay,
  ]);

  const toggleLocalCamera = async () => {
    if (usingWebcam) {
      if (videoRef.current && videoRef.current.srcObject) {
        const stream = videoRef.current.srcObject as MediaStream;
        stream.getTracks().forEach((t) => t.stop());
        videoRef.current.srcObject = null;
      }
      setUsingWebcam(false);
      setWebcamError(null);
      return;
    }

    try {
      setWebcamError(null);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 960, height: 540 },
        audio: false,
      });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
        setUsingWebcam(true);
      }
    } catch {
      setWebcamError('Local camera unavailable — streaming primary AUV stereo optical feed');
      setUsingWebcam(false);
    }
  };

  // Focus & zoom directly onto a specific coral in the video stream
  const focusOnClusterInFeed = (clusterId: string) => {
    onSelectCluster(clusterId);
    const targetAnchors: Record<string, [number, number]> = {
      'C-01': [-0.24, -0.02],
      'C-04': [0.04, -0.04],
      'C-07': [0.27, -0.1],
      'C-13': [0.08, 0.22],
    };
    const anchor = targetAnchors[clusterId] || [0, 0];
    setCamZoom(1.45);
    setCamPan(anchor);
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId = 0;
    const startTime = performance.now();

    const isSoftwareEnv = (() => {
      try {
        const probe = document.createElement('canvas').getContext('webgl2');
        if (!probe) return true;
        const ext = probe.getExtension('WEBGL_debug_renderer_info');
        const param = ext ? ext.UNMASKED_RENDERER_WEBGL : probe.RENDERER;
        const gpu = String(probe.getParameter(param));
        probe.getExtension('WEBGL_lose_context')?.loseContext();
        return /SwiftShader|llvmpipe|softpipe|Software|Basic Render/i.test(gpu);
      } catch {
        return true;
      }
    })();

    const marineSnow = Array.from({ length: 64 }, (_, i) => ({
      x: ((i * 73) % 100) / 100,
      y: ((i * 41) % 100) / 100,
      z: 0.3 + ((i * 19) % 70) / 100,
      size: 1 + (i % 3) * 0.65,
    }));

    // Anchors calibrated to the real coral positions in underwater_coral_reef_panorama
    const coralTargets = [
      {
        clusterId: 'C-01',
        uBase: 0.22,
        vBase: 0.52,
        wNorm: 0.34,
        hNorm: 0.38,
        depthRange: 1.45,
      },
      {
        clusterId: 'C-04',
        uBase: 0.55,
        vBase: 0.51,
        wNorm: 0.23,
        hNorm: 0.36,
        depthRange: 1.65,
      },
      {
        clusterId: 'C-07',
        uBase: 0.8,
        vBase: 0.41,
        wNorm: 0.24,
        hNorm: 0.3,
        depthRange: 1.38,
      },
      {
        clusterId: 'C-13',
        uBase: 0.6,
        vBase: 0.79,
        wNorm: 0.19,
        hNorm: 0.22,
        depthRange: 1.85,
      },
    ];

    const drawViewportChannel = (
      vpX: number,
      vpY: number,
      vpW: number,
      vpH: number,
      channel: 'optical' | 'fluorescence' | 'depth' | 'normals',
      elapsed: number,
      recordBoxes: boolean
    ) => {
      const st = stateRef.current;
      ctx.save();
      ctx.beginPath();
      ctx.rect(vpX, vpY, vpW, vpH);
      ctx.clip();

      // Continuous underwater AUV motion + operator pan/zoom
      const swayX =
        Math.sin(elapsed * 0.68) * 0.018 +
        Math.cos(elapsed * 1.45) * 0.006 +
        st.camPan[0];
      const swayY =
        Math.cos(elapsed * 0.54) * 0.014 +
        Math.sin(elapsed * 1.2) * 0.005 +
        st.camPan[1];

      const zoom = st.camZoom;
      const optImg = opticalImgRef.current;
      const uvImg = uvImgRef.current;

      const sourceImg =
        channel === 'fluorescence' && uvImg && uvImg.complete && uvImg.naturalWidth > 0
          ? uvImg
          : optImg && optImg.complete && optImg.naturalWidth > 0
          ? optImg
          : null;

      if (st.usingWebcam && videoRef.current && videoRef.current.readyState >= 2) {
        ctx.drawImage(videoRef.current, vpX, vpY, vpW, vpH);
      } else if (sourceImg) {
        // Crop inward by 12% to exclude static baked borders and allow smooth live pan/zoom
        const baseCropX = sourceImg.naturalWidth * 0.09;
        const baseCropY = sourceImg.naturalHeight * 0.14;
        const baseCropW = sourceImg.naturalWidth * 0.82;
        const baseCropH = sourceImg.naturalHeight * 0.72;

        const zoomedW = baseCropW / zoom;
        const zoomedH = baseCropH / zoom;
        const sx = Math.max(
          sourceImg.naturalWidth * 0.02,
          Math.min(
            sourceImg.naturalWidth - zoomedW - sourceImg.naturalWidth * 0.02,
            baseCropX + (baseCropW - zoomedW) * 0.5 + swayX * baseCropW * 0.45
          )
        );
        const sy = Math.max(
          sourceImg.naturalHeight * 0.1,
          Math.min(
            sourceImg.naturalHeight - zoomedH - sourceImg.naturalHeight * 0.08,
            baseCropY + (baseCropH - zoomedH) * 0.5 + swayY * baseCropH * 0.45
          )
        );

        ctx.drawImage(sourceImg, sx, sy, zoomedW, zoomedH, vpX, vpY, vpW, vpH);
      } else {
        const bgGrad = ctx.createLinearGradient(vpX, vpY, vpX, vpY + vpH);
        bgGrad.addColorStop(0, '#072432');
        bgGrad.addColorStop(1, '#04121A');
        ctx.fillStyle = bgGrad;
        ctx.fillRect(vpX, vpY, vpW, vpH);
      }

      // Apply channel-specific scientific sensor processing overlays
      if (channel === 'depth') {
        // False-color LiDAR / Stereo Depth Range Heatmap overlay
        const depthGrad = ctx.createLinearGradient(vpX, vpY, vpX, vpY + vpH);
        depthGrad.addColorStop(0, 'rgba(15, 23, 42, 0.72)');
        depthGrad.addColorStop(0.45, 'rgba(6, 182, 212, 0.48)');
        depthGrad.addColorStop(0.78, 'rgba(16, 185, 129, 0.46)');
        depthGrad.addColorStop(1, 'rgba(245, 158, 11, 0.52)');
        ctx.fillStyle = depthGrad;
        ctx.fillRect(vpX, vpY, vpW, vpH);

        // Animated LiDAR scanline & range isolines
        const scanY = vpY + ((elapsed * 95) % vpH);
        ctx.strokeStyle = 'rgba(56, 189, 248, 0.55)';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(vpX, scanY);
        ctx.lineTo(vpX + vpW, scanY);
        ctx.stroke();
      } else if (channel === 'normals') {
        // Surface Normal Vector Field tint (RGB -> XYZ surface orientation)
        ctx.fillStyle = 'rgba(30, 27, 75, 0.58)';
        ctx.fillRect(vpX, vpY, vpW, vpH);

        // Dense surface normal grid arrows
        ctx.strokeStyle = 'rgba(129, 140, 248, 0.35)';
        ctx.lineWidth = 1;
        const step = 38;
        for (let gx = vpX + 20; gx < vpX + vpW - 10; gx += step) {
          for (let gy = vpY + vpH * 0.28; gy < vpY + vpH - 10; gy += step) {
            const nx = Math.sin(gx * 0.02 + elapsed) * 5;
            const ny = -11 - Math.cos(gy * 0.02) * 3;
            ctx.beginPath();
            ctx.moveTo(gx, gy);
            ctx.lineTo(gx + nx, gy + ny);
            ctx.stroke();
          }
        }
      } else if (channel === 'fluorescence') {
        // Subtle 470nm UV excitation beam vignette
        const uvGrad = ctx.createRadialGradient(
          vpX + vpW * 0.5,
          vpY + vpH * 0.55,
          vpW * 0.1,
          vpX + vpW * 0.5,
          vpY + vpH * 0.5,
          vpW * 0.65
        );
        uvGrad.addColorStop(0, 'rgba(16, 185, 129, 0.08)');
        uvGrad.addColorStop(0.6, 'rgba(6, 182, 212, 0.12)');
        uvGrad.addColorStop(1, 'rgba(2, 6, 23, 0.55)');
        ctx.fillStyle = uvGrad;
        ctx.fillRect(vpX, vpY, vpW, vpH);
      } else {
        // Moving underwater sunlight caustic ripples on optical stream
        for (let r = 0; r < 5; r++) {
          const rx =
            vpX +
            vpW * (0.15 + r * 0.18 + Math.sin(elapsed * 0.55 + r * 1.4) * 0.04 - swayX * 0.5);
          const cGrad = ctx.createLinearGradient(rx, vpY, rx + 70, vpY + vpH * 0.85);
          cGrad.addColorStop(0, 'rgba(165, 243, 252, 0.09)');
          cGrad.addColorStop(1, 'rgba(14, 116, 144, 0)');
          ctx.fillStyle = cGrad;
          ctx.beginPath();
          ctx.moveTo(rx - 28, vpY);
          ctx.lineTo(rx + 28, vpY);
          ctx.lineTo(rx + 110, vpY + vpH * 0.9);
          ctx.lineTo(rx - 50, vpY + vpH * 0.9);
          ctx.closePath();
          ctx.fill();
        }
      }

      // Live marine snow & flow vector particulates
      marineSnow.forEach((p, idx) => {
        const px =
          vpX +
          (((p.x * vpW + elapsed * (26 + st.currentSpeedMs * 95) * p.z + idx * 17) % vpW + vpW) %
            vpW);
        const py =
          vpY +
          (((p.y * vpH + Math.sin(elapsed * 1.3 + idx) * 12 * p.z) % vpH + vpH) % vpH);
        ctx.fillStyle =
          channel === 'fluorescence'
            ? `rgba(52, 211, 153, ${0.32 * p.z})`
            : `rgba(224, 242, 254, ${0.28 * p.z})`;
        ctx.beginPath();
        ctx.arc(px, py, p.size, 0, Math.PI * 2);
        ctx.fill();
      });

      // Turbidity veil when elevated
      if (st.turbidity > 0.05) {
        ctx.fillStyle = `rgba(15, 41, 52, ${Math.min(0.55, st.turbidity * 0.65)})`;
        ctx.fillRect(vpX, vpY, vpW, vpH);
      }

      // Compute & draw real-time coral tracking boxes synchronized with pan/sway/zoom
      const boxes: TrackedBoxScreen[] = [];

      coralTargets.forEach((t, idx) => {
        const cluster =
          st.clusters.find((c) => c.id === t.clusterId) || st.clusters[idx] || st.clusters[0];
        if (!cluster) return;

        const uShifted = 0.5 + (t.uBase - 0.5 - swayX * 0.55) * zoom;
        const vShifted = 0.5 + (t.vBase - 0.5 - swayY * 0.55) * zoom;

        const cx = vpX + uShifted * vpW;
        const cy = vpY + vShifted * vpH;
        const bw = t.wNorm * vpW * Math.min(1.35, zoom * 0.95);
        const bh = t.hNorm * vpH * Math.min(1.35, zoom * 0.95);

        const [wx, wy, wz] = projectPixelToWorld(uShifted, vShifted, t.depthRange, {
          x: st.vehiclePos[0],
          y: st.vehiclePos[1],
          depthM: st.vehiclePos[2],
          yawRad: 0.12,
        });

        const conf = Math.min(
          99.4,
          Math.max(78.0, (0.96 - st.turbidity * 0.16 + Math.sin(elapsed * 1.9 + idx) * 0.012) * 100)
        );

        const boxEntry: TrackedBoxScreen = {
          id: cluster.id,
          cluster,
          x: cx - bw * 0.5,
          y: cy - bh * 0.5,
          w: bw,
          h: bh,
          worldX: cluster.localX || wx,
          worldY: cluster.localY || wy,
          worldZ: cluster.depthM || wz,
          confidence: Number(conf.toFixed(1)),
        };
        boxes.push(boxEntry);

        // Draw PCA Surface Normal Vectors if enabled
        if (st.showNormals || channel === 'normals') {
          const [nx, ny, nz] = cluster.surfaceNormal;
          const pca = validatePcaSurfaceNormal(cluster.surfaceNormal);
          ctx.save();
          ctx.strokeStyle = pca.valid ? '#34D399' : '#FBBF24';
          ctx.lineWidth = 1.6;
          ctx.setLineDash([4, 3]);
          ctx.beginPath();
          ctx.ellipse(cx, cy + 8, Math.max(16, bw * 0.22), Math.max(7, bh * 0.09), nx * 0.4, 0, Math.PI * 2);
          ctx.stroke();
          ctx.setLineDash([]);

          const tipX = cx + nx * 52;
          const tipY = cy - nz * 38 + ny * 18;
          ctx.lineWidth = 2.2;
          ctx.beginPath();
          ctx.moveTo(cx, cy + 8);
          ctx.lineTo(tipX, tipY);
          ctx.stroke();

          ctx.fillStyle = pca.valid ? '#34D399' : '#FBBF24';
          ctx.beginPath();
          ctx.arc(tipX, tipY, 3.2, 0, Math.PI * 2);
          ctx.fill();
          ctx.restore();
        }

        // Draw Detection Bounding Boxes
        if (st.showDetections) {
          const isSelected = boxEntry.id === st.selectedClusterId;
          const isHovered = boxEntry.id === st.hoveredBoxId;
          const statusStroke =
            cluster.status === 'Living'
              ? '#6EE7B7'
              : cluster.status === 'Placed'
              ? '#38BDF8'
              : cluster.status === 'Bleached'
              ? '#FBBF24'
              : '#F87171';

          ctx.save();
          ctx.strokeStyle = isSelected ? '#22D3EE' : statusStroke;
          ctx.lineWidth = isSelected || isHovered ? 2.4 : 1.6;

          if (isSelected || isHovered) {
            ctx.fillStyle = 'rgba(34, 211, 238, 0.10)';
            ctx.fillRect(boxEntry.x, boxEntry.y, boxEntry.w, boxEntry.h);
          }
          ctx.strokeRect(boxEntry.x, boxEntry.y, boxEntry.w, boxEntry.h);

          // Top tag (`C-01 · Live · Acropora`)
          const statusShort = cluster.status === 'Living' ? 'Live' : cluster.status;
          const labelText =
            vpW < 420
              ? `${boxEntry.id} · ${statusShort}`
              : `${boxEntry.id} · ${statusShort} · ${cluster.morphology}`;
          ctx.font = '600 11.5px "Plus Jakarta Sans", sans-serif';
          const tagW = ctx.measureText(labelText).width + 14;
          const tagH = 22;
          const tagY = Math.max(vpY + 4, boxEntry.y - tagH);

          ctx.fillStyle = isSelected ? '#22D3EE' : '#E2F1F8';
          ctx.fillRect(boxEntry.x, tagY, tagW, tagH);
          ctx.fillStyle = '#06131A';
          ctx.fillText(labelText, boxEntry.x + 7, tagY + 15);

          // Bottom telemetry strip inside bounding box
          if (vpW >= 420) {
            const subLabel =
              channel === 'fluorescence'
                ? `${cluster.fluorescence.band} · ${boxEntry.confidence}%`
                : `${boxEntry.worldX.toFixed(2)}, ${boxEntry.worldY.toFixed(2)}m · -${boxEntry.worldZ.toFixed(1)}m · ${boxEntry.confidence}%`;
            ctx.font = '500 10.5px "JetBrains Mono", monospace';
            const subW = Math.min(boxEntry.w, ctx.measureText(subLabel).width + 12);
            ctx.fillStyle = 'rgba(6, 17, 24, 0.86)';
            ctx.fillRect(boxEntry.x, boxEntry.y + boxEntry.h - 19, subW, 19);
            ctx.fillStyle = '#BAE6FD';
            ctx.fillText(subLabel, boxEntry.x + 6, boxEntry.y + boxEntry.h - 5);
          }

          ctx.restore();
        }
      });

      if (recordBoxes) {
        trackedBoxesRef.current = boxes;
      }

      // Channel badge in Quad Split mode
      if (vpW < 500) {
        const titles: Record<string, string> = {
          optical: 'CH1 · RGB-D Optical',
          fluorescence: 'CH2 · 470nm UV GFP/RFP',
          depth: 'CH3 · Bathymetric Range',
          normals: 'CH4 · Surface Normals n_k',
        };
        ctx.fillStyle = 'rgba(7, 19, 26, 0.88)';
        ctx.fillRect(vpX + 8, vpY + 8, 158, 20);
        ctx.font = '600 10.5px "JetBrains Mono", monospace';
        ctx.fillStyle = '#7DD3FC';
        ctx.fillText(titles[channel], vpX + 14, vpY + 21);
      }

      ctx.restore();
    };

    // Draw interactive 3D Coral Specimen Turntable PIP in bottom-right corner
    const draw3DSpecimenTurntable = (width: number, height: number, elapsed: number) => {
      const st = stateRef.current;
      if (!st.showTurntableOverlay || st.spectralMode === 'quad') return;

      const sel = st.clusters.find((c) => c.id === st.selectedClusterId) || st.clusters[0];
      if (!sel) return;

      const pipW = 205;
      const pipH = 148;
      const pipX = width - pipW - 12;
      const pipY = height - pipH - 38;

      ctx.save();
      ctx.fillStyle = 'rgba(6, 17, 24, 0.92)';
      ctx.strokeStyle = '#22D3EE';
      ctx.lineWidth = 1.2;
      ctx.fillRect(pipX, pipY, pipW, pipH);
      ctx.strokeRect(pipX, pipY, pipW, pipH);

      const cx = pipX + pipW * 0.5;
      const cy = pipY + pipH * 0.58;
      const spin = st.objectSpinAngle + elapsed * 0.45;

      // Rotating 3D turntable grid ellipse
      ctx.strokeStyle = 'rgba(56, 189, 248, 0.35)';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.ellipse(cx, cy + 22, 56, 16, 0, 0, Math.PI * 2);
      ctx.stroke();

      // Draw rotating 3D coral morphology wireframe/solid based on species morphology
      const col =
        sel.status === 'Living'
          ? '#34D399'
          : sel.status === 'Placed'
          ? '#38BDF8'
          : sel.status === 'Bleached'
          ? '#FBBF24'
          : '#F87171';

      if (sel.morphology === 'tabulate') {
        for (let tier = 0; tier < 3; tier++) {
          const offX = Math.cos(spin + tier * 1.8) * (10 - tier * 2);
          const offY = cy + 6 - tier * 11;
          ctx.fillStyle = col;
          ctx.globalAlpha = 0.35 + tier * 0.2;
          ctx.beginPath();
          ctx.ellipse(cx + offX, offY, 38 - tier * 7, 10 - tier * 1.5, 0, 0, Math.PI * 2);
          ctx.fill();
          ctx.globalAlpha = 0.9;
          ctx.strokeStyle = col;
          ctx.stroke();
        }
      } else if (sel.morphology === 'staghorn') {
        ctx.strokeStyle = col;
        ctx.lineWidth = 3;
        for (let b = 0; b < 9; b++) {
          const ang = (b / 9) * Math.PI * 2 + spin;
          const bx = cx + Math.cos(ang) * 32;
          const by = cy - 18 + Math.sin(ang) * 10;
          ctx.beginPath();
          ctx.moveTo(cx, cy + 16);
          ctx.quadraticCurveTo(cx + Math.cos(ang) * 14, cy, bx, by);
          ctx.stroke();
        }
      } else {
        for (let p = 0; p < 12; p++) {
          const ang = (p / 12) * Math.PI * 2 + spin;
          const rad = 14 + (p % 3) * 9;
          const px = cx + Math.cos(ang) * rad;
          const py = cy + 2 + Math.sin(ang) * (rad * 0.35) - (2 - (p % 3)) * 8;
          ctx.fillStyle = col;
          ctx.globalAlpha = 0.75;
          ctx.beginPath();
          ctx.arc(px, py, 6.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      ctx.globalAlpha = 1;
      // PCA normal arrow on turntable
      ctx.strokeStyle = '#22D3EE';
      ctx.lineWidth = 1.8;
      ctx.beginPath();
      ctx.moveTo(cx, cy + 10);
      ctx.lineTo(cx + sel.surfaceNormal[0] * 35, cy - 32);
      ctx.stroke();

      // Header & footer labels inside PIP
      ctx.fillStyle = '#E0F2FE';
      ctx.font = '600 10.5px "Plus Jakarta Sans", sans-serif';
      ctx.fillText(`3D Lock: ${sel.id} (${sel.morphology})`, pipX + 8, pipY + 15);

      ctx.fillStyle = '#94B4C7';
      ctx.font = '500 9.5px "JetBrains Mono", monospace';
      const deg = Math.round(((spin * 180) / Math.PI) % 360);
      ctx.fillText(
        `Angle ${deg}° · ${sel.boundsM[0]}×${sel.boundsM[1]}×${sel.boundsM[2]}m`,
        pipX + 8,
        pipY + pipH - 8
      );
      ctx.restore();
    };

    const renderFrame = (now: number) => {
      const elapsed = (now - startTime) * 0.001;
      const st = stateRef.current;
      const width = canvas.width;
      const height = canvas.height;

      ctx.clearRect(0, 0, width, height);

      if (st.spectralMode === 'quad') {
        const hw = width * 0.5;
        const hh = height * 0.5;
        drawViewportChannel(0, 0, hw, hh, 'optical', elapsed, true);
        drawViewportChannel(hw, 0, hw, hh, 'fluorescence', elapsed, false);
        drawViewportChannel(0, hh, hw, hh, 'depth', elapsed, false);
        drawViewportChannel(hw, hh, hw, hh, 'normals', elapsed, false);

        // Quad divider crosshairs
        ctx.strokeStyle = '#22D3EE';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.moveTo(hw, 0);
        ctx.lineTo(hw, height);
        ctx.moveTo(0, hh);
        ctx.lineTo(width, hh);
        ctx.stroke();
      } else {
        drawViewportChannel(0, 0, width, height, st.spectralMode, elapsed, true);
        draw3DSpecimenTurntable(width, height, elapsed);
      }

      if (isSoftwareEnv) {
        animId = window.setTimeout(() => renderFrame(performance.now()), 95);
      } else {
        animId = requestAnimationFrame(renderFrame);
      }
    };

    renderFrame(performance.now());
    return () => {
      cancelAnimationFrame(animId);
      clearTimeout(animId);
    };
  }, []);

  const handleMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    setIsDraggingFeed(true);
    dragStartRef.current = {
      x: e.clientX,
      y: e.clientY,
      panX: camPan[0],
      panY: camPan[1],
      spin: objectSpinAngle,
    };
  };

  const handleMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();

    if (isDraggingFeed) {
      const dx = (e.clientX - dragStartRef.current.x) / rect.width;
      const dy = (e.clientY - dragStartRef.current.y) / rect.height;
      setCamPan([
        Math.max(-0.35, Math.min(0.35, Number((dragStartRef.current.panX - dx * 0.6).toFixed(3)))),
        Math.max(-0.35, Math.min(0.35, Number((dragStartRef.current.panY - dy * 0.6).toFixed(3)))),
      ]);
      setObjectSpinAngle(Number((dragStartRef.current.spin + dx * 4.2).toFixed(2)));
      return;
    }

    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;
    const mx = (e.clientX - rect.left) * scaleX;
    const my = (e.clientY - rect.top) * scaleY;

    const hit = trackedBoxesRef.current.find(
      (b) => mx >= b.x && mx <= b.x + b.w && my >= b.y && my <= b.y + b.h
    );
    setHoveredBoxId(hit ? hit.id : null);
  };

  const handleMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const movedDist = Math.hypot(
      e.clientX - dragStartRef.current.x,
      e.clientY - dragStartRef.current.y
    );
    setIsDraggingFeed(false);

    if (movedDist < 6) {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      const clickX = (e.clientX - rect.left) * scaleX;
      const clickY = (e.clientY - rect.top) * scaleY;

      const hit = trackedBoxesRef.current.find(
        (b) => clickX >= b.x && clickX <= b.x + b.w && clickY >= b.y && clickY <= b.y + b.h
      );
      if (hit) {
        onSelectCluster(hit.id);
      }
    }
  };

  const selectedCluster =
    clusters.find((c) => c.id === selectedClusterId) || clusters[0];
  const spectralBands = computeSpectralCurve(selectedCluster);

  return (
    <div className="flex flex-col h-full bg-[#0D1A22] border border-[#1B313E]">
      {/* Compact Header with Mode Tabs & Icon-Only Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5 border-b border-[#1B313E]">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-[#F0F7FA] tracking-tight">Live Camera</h2>
          <div className="flex items-center bg-[#081218] border border-[#1E3645] p-0.5 text-xs">
            {(
              [
                ['optical', 'Optical'],
                ['fluorescence', 'UV Glow'],
                ['depth', 'Depth'],
                ['normals', 'Normals'],
                ['quad', '4-View'],
              ] as const
            ).map(([mode, label]) => (
              <button
                key={mode}
                type="button"
                onClick={() => setSpectralMode(mode)}
                className={`px-2 py-0.5 font-medium transition-colors whitespace-nowrap cursor-pointer ${
                  spectralMode === mode
                    ? 'bg-[#163849] text-white'
                    : 'text-[#8BA6B8] hover:text-white'
                }`}
              >
                {label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={toggleLocalCamera}
            title={usingWebcam ? 'Stop webcam' : 'Use local camera'}
            aria-label={usingWebcam ? 'Stop webcam' : 'Use local camera'}
            className={`p-1.5 border transition-colors cursor-pointer ${
              usingWebcam
                ? 'bg-[#153445] border-[#38BDF8] text-[#E0F2FE]'
                : 'bg-[#091318] border-[#233F4F] text-[#94B4C7] hover:text-white'
            }`}
          >
            <Camera className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={() => setShowDetections((v) => !v)}
            aria-pressed={showDetections}
            title="Toggle detection boxes"
            aria-label="Toggle detection boxes"
            className={`p-1.5 border transition-colors cursor-pointer ${
              showDetections
                ? 'bg-[#12313B] border-[#34D399]/70 text-[#6EE7B7]'
                : 'bg-[#091318] border-[#233F4F] text-[#8BA6B8] hover:text-white'
            }`}
          >
            <Eye className="w-3.5 h-3.5" />
          </button>

          <button
            type="button"
            onClick={() => setShowTurntableOverlay((v) => !v)}
            aria-pressed={showTurntableOverlay}
            title="Toggle 3D Specimen PIP"
            aria-label="Toggle 3D Specimen PIP"
            className={`p-1.5 border transition-colors cursor-pointer ${
              showTurntableOverlay
                ? 'bg-[#122C3B] border-[#38BDF8]/70 text-[#7DD3FC]'
                : 'bg-[#091318] border-[#233F4F] text-[#8BA6B8] hover:text-white'
            }`}
          >
            <Box className="w-3.5 h-3.5" />
          </button>

          {onSwapSlot && (
            <button
              type="button"
              onClick={onSwapSlot}
              title="Swap panel position"
              aria-label="Swap Live Camera panel position"
              className="p-1.5 bg-[#091318] border border-[#233F4F] text-[#8BA6B8] hover:text-white cursor-pointer"
            >
              <ArrowLeftRight className="w-3.5 h-3.5" />
            </button>
          )}

          {onToggleExpand && (
            <button
              type="button"
              onClick={onToggleExpand}
              title={isExpanded ? 'Restore 2×2 grid' : 'Expand full width'}
              aria-label={isExpanded ? 'Restore 2×2 grid' : 'Expand full width'}
              className="p-1.5 bg-[#091318] border border-[#233F4F] text-[#8BA6B8] hover:text-white cursor-pointer"
            >
              {isExpanded ? (
                <Minimize2 className="w-3.5 h-3.5" />
              ) : (
                <Maximize2 className="w-3.5 h-3.5" />
              )}
            </button>
          )}
        </div>
      </div>

      {/* Video Canvas Viewport */}
      <div className="relative flex-1 min-h-[290px] bg-[#061117] overflow-hidden select-none">
        <video ref={videoRef} className="hidden" playsInline muted />
        <canvas
          ref={canvasRef}
          width={800}
          height={430}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={() => setIsDraggingFeed(false)}
          aria-label="Live underwater AUV stereo camera stream"
          className={`w-full h-full object-cover block ${
            isDraggingFeed
              ? 'cursor-grabbing'
              : hoveredBoxId
              ? 'cursor-pointer'
              : 'cursor-grab'
          }`}
        />

        {/* Compact Top-Right Icon-Only Spin & Zoom Dock */}
        <div className="absolute top-2.5 right-2.5 flex items-center gap-0.5 bg-[#07131A]/90 border border-[#244254] px-1.5 py-1 text-xs font-mono text-[#BAE6FD]">
          <button
            type="button"
            onClick={() => setObjectSpinAngle((a) => Number((a - 0.45).toFixed(2)))}
            aria-label="Spin coral counter-clockwise"
            className="p-1 hover:text-white cursor-pointer"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setObjectSpinAngle((a) => Number((a + 0.45).toFixed(2)))}
            aria-label="Spin coral clockwise"
            className="p-1 hover:text-white cursor-pointer"
          >
            <RotateCw className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setCamZoom((z) => Math.min(2.6, Number((z + 0.25).toFixed(2))))}
            aria-label="Zoom in camera feed"
            className="p-1 hover:text-white cursor-pointer"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={() => setCamZoom((z) => Math.max(1.0, Number((z - 0.25).toFixed(2))))}
            aria-label="Zoom out camera feed"
            className="p-1 hover:text-white cursor-pointer"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          {camZoom > 1.0 && (
            <button
              type="button"
              onClick={() => {
                setCamZoom(1.0);
                setCamPan([0, 0]);
              }}
              className="px-1.5 py-0.5 text-[10px] bg-[#122C3B] text-white cursor-pointer"
            >
              1×
            </button>
          )}
        </div>

        {/* Compact Bottom Quick Target Selector */}
        <div className="absolute bottom-2 left-2.5 right-2.5 flex items-center justify-between gap-2 text-xs pointer-events-none">
          <div className="flex items-center gap-1 pointer-events-auto bg-[#07131A]/90 border border-[#1F3A4B] p-1">
            {(['C-01', 'C-03', 'C-04', 'C-07', 'C-13'] as const).map((cid) => (
              <button
                key={cid}
                type="button"
                onClick={() => focusOnClusterInFeed(cid)}
                className={`px-2 py-0.5 font-mono text-[11px] transition-colors cursor-pointer ${
                  selectedClusterId === cid
                    ? 'bg-[#15394A] text-[#38BDF8] font-bold'
                    : 'text-[#94B4C7] hover:text-white'
                }`}
              >
                {cid}
              </button>
            ))}
          </div>
          <span className="px-2 py-1 bg-[#07131A]/90 border border-[#1F3A4B] font-mono text-[11px] text-[#7DD3FC] tabular-nums">
            {selectedCluster.id} · {selectedCluster.morphology} · {(selectedCluster.confidence * 100).toFixed(0)}%
          </span>
        </div>
      </div>

      {/* Live Interactive UV Biofluorescence & Spectral Graph (450nm – 685nm) */}
      <div className="px-4 py-2.5 border-t border-[#1B313E] bg-[#0A151C] flex items-center gap-4">
        <div className="shrink-0">
          <div className="text-[11px] text-[#8BA6B8]">Spectral Fluorescence</div>
          <div className="text-xs font-mono font-bold text-[#34D399] tabular-nums">
            {selectedCluster.id} · {selectedCluster.fluorescence.band.split(' ')[0]}
          </div>
        </div>

        <svg
          viewBox="0 0 320 42"
          className="flex-1 h-11 overflow-visible select-none"
          aria-label="Interactive coral fluorescence spectral graph"
        >
          <defs>
            <linearGradient id="specCurveGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#34D399" stopOpacity="0.4" />
              <stop offset="100%" stopColor="#38BDF8" stopOpacity="0.05" />
            </linearGradient>
          </defs>
          <line x1="0" y1="32" x2="320" y2="32" stroke="#162B38" strokeWidth="1" />

          {/* Smooth Spectral Polygon Area */}
          <polygon
            fill="url(#specCurveGrad)"
            points={`14,32 ${spectralBands
              .map((b, i) => {
                const x = 14 + (i / (spectralBands.length - 1)) * 292;
                const y = 32 - (b.intensityPct / 100) * 26;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
              })
              .join(' ')} 306,32`}
          />
          <polyline
            fill="none"
            stroke="#34D399"
            strokeWidth="1.8"
            points={spectralBands
              .map((b, i) => {
                const x = 14 + (i / (spectralBands.length - 1)) * 292;
                const y = 32 - (b.intensityPct / 100) * 26;
                return `${x.toFixed(1)},${y.toFixed(1)}`;
              })
              .join(' ')}
          />

          {spectralBands.map((b, i) => {
            const x = 14 + (i / (spectralBands.length - 1)) * 292;
            const y = 32 - (b.intensityPct / 100) * 26;
            const dotCol =
              b.wavelengthNm === 508
                ? '#34D399'
                : b.wavelengthNm === 585
                ? '#FBBF24'
                : '#38BDF8';
            return (
              <g key={b.wavelengthNm}>
                <circle cx={x} cy={y} r="2.8" fill={dotCol} />
                <text
                  x={x}
                  y="41"
                  textAnchor="middle"
                  fill="#7FA0B5"
                  fontSize="8.5"
                  fontFamily="JetBrains Mono, monospace"
                >
                  {b.wavelengthNm}
                </text>
                <text
                  x={x}
                  y={Math.max(8, y - 4)}
                  textAnchor="middle"
                  fill="#E6F0F5"
                  fontSize="8"
                  fontFamily="JetBrains Mono, monospace"
                >
                  {b.intensityPct}%
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
};
