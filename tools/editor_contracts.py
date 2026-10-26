"""Shared fail-closed file-editor contracts; never verifies live state."""
import os
import shutil
import math


def integer(value, name, minimum=0, maximum=2**31 - 1):
    """Require an integer without bool/coercion, in an explicit domain."""
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'{name} must be an integer in {minimum}..{maximum} (not bool)')
    return value


def boolean(value, name):
    if type(value) is not bool:
        raise ValueError(f'{name} must be boolean')
    return value


def number(value, name):
    """Finite binary64 numeric input, without string/bool coercion."""
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except (OverflowError, ValueError):
        valid = False
    if not valid:
        raise ValueError(f'{name} must be a finite number (not bool)')
    return value


def input_error(ints=None, bools=None, numbers=None):
    try:
        for name, value in (ints or {}).items():
            integer(value, name)
        for name, value in (bools or {}).items():
            boolean(value, name)
        for name, value in (numbers or {}).items():
            number(value, name)
    except ValueError as exc:
        return {'ok': False, 'written': False, 'error': str(exc)}
    return None

import patchio


def save_edit(out, path, document, backup_suffix=None, load_requested=False,
              loader=None, writer=None):
    """Business backup and atomic patchio write, then at most one reload."""
    out.update(written=False, written_path=None, load_requested=bool(load_requested),
               loaded=False, load_succeeded=None, verified=False, stage='backup')
    if backup_suffix:
        try:
            backup = path + backup_suffix
            shutil.copy2(path, backup)
        except Exception as exc:
            out.update(ok=False, stage='backup_failed', error=f'Backup failed; no write: {exc}')
            return out
        out['backup'] = backup
    try:
        (writer or patchio.write_patch)(path, document)
    except Exception as exc:
        out.update(ok=False, stage='write_failed', error=f'Write failed: {exc}')
        return out
    out.update(ok=True, written=path)
    return after_write(out, path, load_requested, loader)


def after_write(out, path, load_requested=False, loader=None):
    """Annotate an already successful write, preserving legacy written types."""
    out.setdefault('ok', True)
    out.setdefault('written', path)
    out.update(written_path=os.path.abspath(path), load_requested=bool(load_requested),
               loaded=False, load_succeeded=None, verified=False, stage='written')
    if not load_requested:
        return out
    if loader is None:
        import cardinal_mcp
        loader = cardinal_mcp.load_patch
    # Once invoked, a loader may have replaced the rack even if it throws.
    # Never turn unknown effects into loaded=False or retry automatically.
    out['loaded'] = None
    out['stage'] = 'load_unknown'
    try:
        result = loader(out['written_path'])
    except Exception as exc:
        out.update(ok=False, error=f'Load raised after successful write: {exc}')
        return out
    out['loaded'] = result  # Preserve the legacy raw dict (or malformed reply).
    if isinstance(result, dict) and type(result.get('ok')) is bool:
        clean = (result['ok'] and not any(result.get(k) for k in ('error', 'warning', 'warnings')))
        out.update(ok=out['ok'] and clean, load_succeeded=clean,
                   stage='load_succeeded' if clean else 'load_failed')
        if not clean:
            out['error'] = 'File written; loader reported failure or warnings (see loaded)'
    else:
        out.update(ok=False, error='File written; loader result is unknown or malformed')
    return out


def select_target(modules, eligible, name=None, module_id=None):
    """Select exactly one supported module; never infer an id from a name."""
    candidates = [{'module_id': m.get('id'), 'plugin': m.get('plugin'),
                   'model': m.get('model')} for m in eligible]
    qualified = name.replace('|', '/') if name else ''
    if '/' in qualified:
        plugin, model = qualified.casefold().split('/', 1)
        hits = [m for m in eligible if str(m.get('plugin')).casefold() == plugin
                and str(m.get('model')).casefold() == model]
    else:
        hits = [m for m in eligible if not name or
                name.casefold() in f"{m.get('plugin')}|{m.get('model')}".casefold()]
    if module_id is not None:
        if type(module_id) is not int or not 0 <= module_id < 2**63:
            return None, {'ok': False, 'error': 'module_id must be a nonnegative int64 (not bool)',
                          'candidates': candidates}
        id_hits = [m for m in modules if type(m.get('id')) is int and m['id'] == module_id]
        if len(id_hits) != 1:
            return None, {'ok': False, 'error': 'module_id missing or duplicated',
                          'candidates': candidates}
        hits = [m for m in hits if m is id_hits[0]]
    if len(hits) != 1:
        return None, {'ok': False, 'error': 'Target must match exactly one module',
                      'candidates': candidates}
    identity = hits[0].get('id')
    if (type(identity) is not int or not 0 <= identity < 2**63 or
            sum(m.get('id') == identity for m in modules) != 1):
        return None, {'ok': False, 'error': 'Selected module has an invalid or duplicate id',
                      'candidates': candidates}
    return hits[0], None
