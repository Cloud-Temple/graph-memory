#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Vérifie que tous les paramètres des tools MCP ont une description
via le pattern Annotated[type, Field(description="...")].

Usage:
    python3 scripts/check_param_descriptions.py
"""

import re
import sys
import os


def check_server_params(filepath: str) -> dict:
    """Analyse server.py et vérifie les paramètres des tools MCP."""
    
    with open(filepath) as f:
        content = f.read()
    
    # Trouver tous les @mcp.tool() et analyser les signatures
    tools = re.findall(
        r'@mcp\.tool\(\)\nasync def (\w+)\((.*?)\) -> dict:',
        content, re.DOTALL
    )
    
    results = {
        "tools": [],
        "total_tools": len(tools),
        "total_user_params": 0,
        "total_annotated": 0,
        "total_ctx": 0,
        "total_no_param": 0,
        "issues": [],
    }
    
    for tool_name, params_str in tools:
        params_str = params_str.strip()
        
        # Tools sans paramètre
        if not params_str:
            results["total_no_param"] += 1
            results["tools"].append({
                "name": tool_name,
                "user_params": 0,
                "annotated": 0,
                "ctx": False,
                "issues": [],
            })
            continue
        
        # Analyser chaque ligne de paramètre
        lines = [l.strip() for l in params_str.split('\n') if l.strip()]
        
        tool_user = 0
        tool_annotated = 0
        tool_ctx = False
        tool_issues = []
        
        for line in lines:
            line = line.rstrip(',')
            if not line or ':' not in line:
                continue
            
            param_name = line.split(':')[0].strip()
            
            # ctx est interne FastMCP, pas besoin de description
            if param_name == 'ctx':
                tool_ctx = True
                results["total_ctx"] += 1
                continue
            
            tool_user += 1
            results["total_user_params"] += 1
            
            if 'Annotated[' in line and 'description=' in line:
                tool_annotated += 1
                results["total_annotated"] += 1
            else:
                tool_issues.append(param_name)
                results["issues"].append(f"{tool_name}.{param_name}")
        
        results["tools"].append({
            "name": tool_name,
            "user_params": tool_user,
            "annotated": tool_annotated,
            "ctx": tool_ctx,
            "issues": tool_issues,
        })
    
    return results


def main():
    """Point d'entrée principal."""
    
    # Trouver le fichier server.py
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    filepath = os.path.join(project_root, "src", "mcp_memory", "server.py")
    
    if not os.path.exists(filepath):
        print(f"❌ Fichier non trouvé : {filepath}")
        sys.exit(1)
    
    print(f"📋 Vérification des descriptions de paramètres MCP")
    print(f"   Fichier : {filepath}")
    print()
    
    results = check_server_params(filepath)
    
    # Afficher le détail par tool
    for tool in results["tools"]:
        name = tool["name"]
        user = tool["user_params"]
        anno = tool["annotated"]
        ctx = " + ctx" if tool["ctx"] else ""
        
        if user == 0:
            status = "✅ (aucun paramètre)"
        elif not tool["issues"]:
            status = "✅"
        else:
            status = f"⚠️  MANQUANTS: {tool['issues']}"
        
        print(f"  {name:30s} : {anno:2d}/{user} params{ctx}  {status}")
    
    # Résumé
    print()
    print("=" * 60)
    print(f"  Tools totaux        : {results['total_tools']}")
    print(f"  Sans paramètre      : {results['total_no_param']}")
    print(f"  Params utilisateur  : {results['total_annotated']}/{results['total_user_params']} avec Annotated")
    print(f"  Params ctx          : {results['total_ctx']} (sans description, OK)")
    print(f"  Issues              : {len(results['issues'])}")
    print("=" * 60)
    
    if results["issues"]:
        print(f"\n⚠️  Paramètres sans Annotated[type, Field(description=...)] :")
        for issue in results["issues"]:
            print(f"    - {issue}")
        sys.exit(1)
    else:
        print(f"\n✅ TOUS les {results['total_annotated']} paramètres utilisateur ont")
        print(f"   Annotated[type, Field(description=...)]")
        print(f"   → Aucun 'No description' dans Cline !")
        sys.exit(0)


if __name__ == "__main__":
    main()
