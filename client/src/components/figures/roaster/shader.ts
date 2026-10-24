/**
 * The figure's two WebGL layers, in the drawing's own iso camera (GLSL_ISO). Everything is built
 * from world points: each flame stands on its jet's axis, the light lands on the burner box's own
 * floor and wall, and the smoke rises from the stack's lip. Every term rides an envelope set in
 * the live component (gas, smoke, steam) and falls to zero well inside the canvas.
 */

/** Blue gas flames on the jets, and their light on the burner box's floor and back wall. */
export const FIRE = `
uniform float uGas;
uniform float uJets[5];
uniform vec2 uJet;
uniform vec4 uBox;
uniform vec2 uWall;
const float RFLAME=2.3;

vec3 flameAt(vec2 vb,float jy,float seed,float px){
  vec3 V=towardViewer();
  vec2 h=normalize(V.xy);
  vec3 p0=rayOf(vb);
  vec2 J=vec2(0.,jy);
  float t=dot(J-p0.xy,h)/dot(V.xy,h);
  vec3 p=p0+t*V;
  float u=dot(p.xy-J,vec2(-h.y,h.x));
  float s=p.z-uJet.x;
  float H=uJet.y*mix(.25,1.,uGas)*(1.+.09*(noise2(vec2(uTime*3.1,seed))-.5));
  float q=s/H;
  float sway=(noise2(vec2(s*.22-uTime*5.2,seed*3.7))-.5)*1.3*q*q;
  float uu=u-sway;
  float w=RFLAME*(1.+1.1*q)*sqrt(max(1.-q,0.))+.001;
  float soft=max(.35,.9*px);
  float body=(1.-smoothstep(w-soft,w+soft,abs(uu)))*smoothstep(-.3,.6,s)*(1.-smoothstep(.82,1.,q));
  float edge=body*smoothstep(.25*w,w,abs(uu));
  float qc=s/(H*.55);
  float wc=.72*RFLAME*sqrt(max(1.-qc,0.))*(1.-.2*qc)+.001;
  float core=(1.-smoothstep(wc-soft,wc+soft,abs(uu)))*smoothstep(-.2,.4,s)*(1.-smoothstep(.85,1.,qc));
  float flick=.75+.5*noise2(vec2(s*.5-uTime*9.,seed*1.9+uu*.4));
  vec3 mantle=vec3(.16,.3,1.)*(1.25*body+.7*edge)*flick*(1.-.45*q);
  vec3 inner=vec3(.5,.82,1.)*core*1.5;
  float tipZone=smoothstep(.55,.95,q)*body*smoothstep(.65,1.,uGas)*smoothstep(.55,.9,noise2(vec2(s*.4-uTime*7.,seed*5.1+uu)));
  vec3 tips=vec3(1.,.55,.18)*tipZone*.55;
  return mantle+inner+tips;
}

float inBox(vec2 v,vec2 lo,vec2 hi,float soft){
  return smoothstep(lo.x-soft,lo.x+soft,v.x)*(1.-smoothstep(hi.x-soft,hi.x+soft,v.x))*smoothstep(lo.y-soft,lo.y+soft,v.y)*(1.-smoothstep(hi.y-soft,hi.y+soft,v.y));
}

void main(){
  vec2 vb=viewOf(gl_FragCoord.xy);
  float px=pixelOf();
  vec3 col=vec3(0.);
  if(uGas>.001){
    for(int i=0;i<5;i++)col+=flameAt(vb,uJets[i],float(i)*7.13+1.,px);
    // Their light on the floor of the burner box and on its back wall.
    vec3 f=onFloor(vb,uBox.w);
    vec3 w=onWallX(vb,uBox.x);
    float lf=0.;
    float lw=0.;
    float mid=uJet.x+uJet.y*mix(.25,1.,uGas)*.4;
    for(int i=0;i<5;i++){
      vec3 c=vec3(0.,uJets[i],mid);
      lf+=1./(1.+dot(f-c,f-c)/120.);
      lw+=1./(1.+dot(w-c,w-c)/260.);
    }
    lf*=inBox(f.xy,vec2(uBox.x,uBox.y),vec2(uWall.x,uBox.z),1.2);
    lw*=inBox(w.yz,vec2(uBox.y,uBox.w),vec2(uBox.z,uWall.y),1.2);
    col+=vec3(.12,.2,.75)*(lf*.16+lw*.12)*uGas;
  }
  col=tonemap(col,1.25);
  float m=max(col.r,max(col.g,col.b));
  float n=(hash12(gl_FragCoord.xy+fract(uTime*.61)*91.)+hash12(gl_FragCoord.yx*1.37+fract(uTime*.37)*57.)-1.)/255.;
  col=max(col+n*smoothstep(0.,1.5/255.,m),0.);
  gl_FragColor=vec4(col,max(col.r,max(col.g,col.b)));
}
`

/** Smoke from the stack (steam at a light roast, grey-brown into second crack), steam off the tray. */
export const AIR = `
uniform float uSmoke;
uniform float uDark;
uniform float uSteam;
uniform vec4 uStack;
uniform vec4 uTray;

float column(vec2 vb,vec3 base,float r0,float grow,float height,vec2 drift,float rise,float seed){
  vec3 V=towardViewer();
  vec2 h=normalize(V.xy);
  vec3 p0=rayOf(vb);
  float t=dot(base.xy-p0.xy,h)/dot(V.xy,h);
  vec3 p=p0+t*V;
  float s=p.z-base.z;
  vec2 axis=base.xy+drift*s;
  float u=dot(p.xy-axis,vec2(-h.y,h.x));
  float sig=r0+grow*s;
  float roll=fbm3(vec3(u*.11,(s-uTime*rise)*.07,seed+uTime*.05));
  float d=exp(-u*u/(sig*sig))*smoothstep(-.5,3.,s)*(1.-smoothstep(height*.35,height,s));
  return d*smoothstep(.28,.85,roll+.15*(1.-s/height));
}

void main(){
  vec2 vb=viewOf(gl_FragCoord.xy);
  vec3 col=vec3(0.);
  if(uSmoke>.001){
    float d=column(vb,uStack.xyz,uStack.w,.2,46.,vec2(.22,-.12),13.,3.1);
    vec3 steam=vec3(.82,.84,.88);
    vec3 smoke=vec3(.62,.57,.53);
    col+=mix(steam,smoke,uDark)*d*uSmoke*.55;
  }
  if(uSteam>.001){
    for(int i=0;i<3;i++){
      float a=float(i)*2.1+.4;
      vec3 b=vec3(uTray.x+cos(a)*uTray.w*.45,uTray.y+sin(a)*uTray.w*.45,uTray.z);
      col+=vec3(.8,.82,.86)*column(vb,b,3.5,.16,34.,vec2(.05,-.04),7.,float(i)*4.3)*uSteam*.42;
    }
  }
  col=tonemap(col,1.2);
  float m=max(col.r,max(col.g,col.b));
  float n=(hash12(gl_FragCoord.xy+fract(uTime*.61)*91.)+hash12(gl_FragCoord.yx*1.37+fract(uTime*.37)*57.)-1.)/255.;
  col=max(col+n*smoothstep(0.,1.5/255.,m),0.);
  gl_FragColor=vec4(col,max(col.r,max(col.g,col.b)));
}
`
