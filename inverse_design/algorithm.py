# AUTOGENERATED! DO NOT EDIT! File to edit: notebooks/02_algorithm.ipynb (unless otherwise specified).

__all__ = ['UNASSIGNED', 'VOID', 'SOLID', 'PIXEL_IMPOSSIBLE', 'PIXEL_EXISTING', 'PIXEL_POSSIBLE', 'PIXEL_REQUIRED',
           'TOUCH_REQUIRED', 'TOUCH_INVALID', 'TOUCH_EXISTING', 'TOUCH_VALID', 'TOUCH_FREE', 'TOUCH_RESOLVING',
           'Design', 'new_design', 'circular_brush', 'notched_square_brush', 'show_mask', 'visualize', 'add_void_touch',
           'take_free_void_touches']

# Internal Cell
from typing import NamedTuple

import jax
import jax.numpy as jnp
import matplotlib.pyplot as plt
from fastcore.basics import patch_to
from .utils import batch_conv2d, conv2d, dilute
from matplotlib.colors import ListedColormap

# Cell
UNASSIGNED = 0
VOID = 1
SOLID = 2
PIXEL_IMPOSSIBLE = 3
PIXEL_EXISTING = 4
PIXEL_POSSIBLE = 5
PIXEL_REQUIRED = 6
TOUCH_REQUIRED = 7
TOUCH_INVALID = 8
TOUCH_EXISTING = 9
TOUCH_VALID = 10
TOUCH_FREE = 11
TOUCH_RESOLVING = 12

# Cell
class Design(NamedTuple):
    design: jnp.ndarray
    void_pixels: jnp.ndarray
    solid_pixels: jnp.ndarray
    void_touches: jnp.ndarray
    solid_touches: jnp.ndarray

    @property
    def shape(self):
        return self.design.shape

    def copy(self, **kwargs):
        kwargs = {name: kwargs.get(name, getattr(self, name)) for name in self._fields}
        return Design(*kwargs.values())

# Cell
def new_design(shape):
    return Design(
        design=jnp.zeros(shape, dtype=jnp.uint8).at[:,:].set(UNASSIGNED),
        void_pixels=jnp.zeros(shape, dtype=jnp.uint8).at[:,:].set(PIXEL_POSSIBLE),
        solid_pixels=jnp.zeros(shape, dtype=jnp.uint8).at[:,:].set(PIXEL_POSSIBLE),
        void_touches=jnp.zeros(shape, dtype=jnp.uint8).at[:,:].set(TOUCH_VALID),
        solid_touches=jnp.zeros(shape, dtype=jnp.uint8).at[:,:].set(TOUCH_VALID),
    )

# Cell
def circular_brush(diameter):
    radius = diameter / 2
    X, Y = jnp.mgrid[-radius:radius:1j*diameter,-radius:radius:1j*diameter]
    _int = lambda x: jnp.array(x, dtype=int)
    brush = _int(X)**2 + _int(Y)**2 < radius**2
    return brush

# Cell
def notched_square_brush(diameter):
    if diameter != 5:
        raise NotImplementedError("Can only create notched square brush of size 5")
    radius = diameter / 2
    X, Y = jnp.mgrid[-radius:radius:1j*diameter,-radius:radius:1j*diameter]
    Z = jnp.ones_like(X)
    Z = Z.at[0,0].set(0)
    Z = Z.at[0,-1].set(0)
    Z = Z.at[-1,0].set(0)
    Z = Z.at[-1,-1].set(0)
    return Z > 0.5

# Cell
def show_mask(brush):
    nx, ny = brush.shape
    _cmap = ListedColormap(colors={0: "#ffffff", 1: "#929292"}.values())
    ax = plt.gca()
    ax.set_yticks(jnp.arange(nx)+0.5, ["" for i in range(nx)])
    ax.set_xticks(jnp.arange(ny)+0.5, ["" for i in range(ny)])
    ax.set_yticks(jnp.arange(nx), [f"{i}" for i in range(nx)], minor=True)
    ax.set_xticks(jnp.arange(ny), [f"{i}" for i in range(ny)], minor=True)
    plt.grid(True, color='k')
    plt.imshow(brush, cmap=_cmap)

# Cell
def visualize(design):
    _cmap = ListedColormap(colors={UNASSIGNED: "#929292", VOID: "#cbcbcb", SOLID: "#515151", PIXEL_IMPOSSIBLE: "#8dd3c7", PIXEL_EXISTING: "#ffffb3", PIXEL_POSSIBLE: "#bebada", PIXEL_REQUIRED: "#fb7f72", TOUCH_REQUIRED: "#00ff00", TOUCH_INVALID: "#7fb1d3", TOUCH_EXISTING: "#fdb462", TOUCH_VALID: "#b3de69", TOUCH_FREE: "#fccde5", TOUCH_RESOLVING: "#e0e0e0"}.values(), name="cmap")
    nx, ny = design.design.shape
    fig, axs = plt.subplots(1, 5, figsize=(15,3*nx/ny))
    for i, title in enumerate(design._fields):
        ax = axs[i]
        ax.set_title(title.replace("_", " "))
        ax.imshow(design[i], cmap=_cmap, vmin=UNASSIGNED, vmax=TOUCH_RESOLVING)
        ax.set_yticks(jnp.arange(nx)+0.5, ["" for i in range(nx)])
        ax.set_xticks(jnp.arange(ny)+0.5, ["" for i in range(ny)])
        ax.set_yticks(jnp.arange(nx), [f"{i}" for i in range(nx)], minor=True)
        ax.set_xticks(jnp.arange(ny), [f"{i}" for i in range(ny)], minor=True)
        ax.set_xlim(-0.5, ny-0.5)
        ax.set_ylim(nx-0.5, -0.5)
        ax.grid(visible=True, which="major", c="k")

@patch_to(Design)
def _repr_html_(self):
    visualize(self)
    return ""


# Cell

@jax.jit
def _find_free_touches(touches_mask, pixels_mask, brush):
    r = jnp.zeros_like(touches_mask, dtype=bool)
    m, n = r.shape
    i, j = jnp.arange(m), jnp.arange(n)
    I, J = [idxs.ravel() for idxs in jnp.meshgrid(i, j)]
    K = jnp.arange(m * n)
    R = jnp.broadcast_to(r[None, :, :], (m * n, m, n)).at[K, I, J].set(True)
    Rb = batch_conv2d(R, brush[None]) | pixels_mask
    free_idxs = (Rb == pixels_mask).all((1, 2))
    free_touches_mask = jnp.where(free_idxs[:, None, None], R, 0).sum(0, dtype=bool)
    return free_touches_mask ^ touches_mask


@jax.jit
def _find_required_pixels(pixel_map, brush):
    mask = (~pixel_map) & (~dilute(pixel_map, brush))
    return ~(dilute(mask, brush) | pixel_map)


@jax.jit
def add_void_touch(design, brush, pos):
    if isinstance(pos, tuple):
        void_touches_mask = design.void_touches.at[pos[0], pos[1]].set(TOUCH_EXISTING) == TOUCH_EXISTING
    else:
        assert pos.dtype == bool
        void_touches_mask = pos | (design.void_touches == TOUCH_EXISTING)
    void_pixel_mask = dilute(void_touches_mask, brush) | (design.design == VOID)
    required_void_pixel_mask = _find_required_pixels(void_pixel_mask, brush)
    diluted_mask = dilute(void_pixel_mask, brush)
    design_ = jnp.where(void_pixel_mask, VOID, design.design)
    free_void_touches_mask = _find_free_touches(void_touches_mask, void_pixel_mask | required_void_pixel_mask, brush)
    void_touches = jnp.where(design.void_touches == TOUCH_RESOLVING, TOUCH_VALID, design.void_touches)
    void_touches = jnp.where(void_touches_mask, TOUCH_EXISTING, void_touches)
    void_touches = jnp.where(free_void_touches_mask, TOUCH_FREE, void_touches)
    resolving_pixels = jnp.where(void_touches == TOUCH_VALID, dilute(required_void_pixel_mask, brush), False)
    void_touches = jnp.where(resolving_pixels, TOUCH_RESOLVING, void_touches)
    void_pixels = jnp.where(void_pixel_mask, PIXEL_EXISTING, design.void_pixels)
    void_pixels = jnp.where(required_void_pixel_mask, PIXEL_REQUIRED, void_pixels)
    solid_pixels =  jnp.where(void_pixel_mask, PIXEL_IMPOSSIBLE, design.solid_pixels)
    solid_pixels = jnp.where(required_void_pixel_mask, PIXEL_IMPOSSIBLE, solid_pixels)
    solid_touches = jnp.where(diluted_mask, TOUCH_INVALID, design.solid_touches)
    return Design(design_, void_pixels, solid_pixels, void_touches, solid_touches)

# Cell
@jax.jit
def take_free_void_touches(design, brush):
    # originally:
    # design = design.copy(void_touches=jnp.where(design.void_touches == TOUCH_FREE, TOUCH_EXISTING, design.void_touches))
    # ⬆ the above solution is not good. It does not resolve required touches if present, we need to actually use the brush:
    return add_void_touch(design, brush, (design.void_touches == TOUCH_FREE))