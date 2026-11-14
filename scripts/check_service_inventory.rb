#!/usr/bin/env ruby
# frozen_string_literal: true

# Check that render.yaml and the canonical deployment inventory agree.
# Ported from check_service_inventory.py; standard library only.

require "json"
require "pathname"

ROOT = Pathname.new(__dir__).join("..").expand_path
INVENTORY_PATH = ROOT.join("deploy", "service-inventory.json")
RENDER_PATH = ROOT.join("render.yaml")

def render_service_blocks(text)
  blocks = text.split(/^  - type: /)[1..] || []
  services = {}
  blocks.each do |block|
    name_match = block.match(/^    name:\s*([^\s#]+)/)
    services[name_match[1]] = block if name_match
  end
  services
end

def required_keys(block)
  block.scan(/^\s{6}- key:\s*([A-Za-z0-9_]+)/).flatten.uniq
end

def main
  inventory = JSON.parse(INVENTORY_PATH.read(encoding: "UTF-8"))
  render_services = render_service_blocks(RENDER_PATH.read(encoding: "UTF-8"))
  expected = {}
  inventory.fetch("render_services").each do |item|
    expected[item["name"]] = item if item["render_blueprint"] == true
  end
  errors = []

  canonical_services = expected.select { |_name, item| item["status"] == "active" }.keys
  if render_services.keys.sort != canonical_services.sort
    errors << "render.yaml services must exactly match active canonical inventory services"
  end

  expected.each do |name, item|
    next unless render_services.key?(name)

    block = render_services[name]
    branch = block.match(/^    branch:\s*([^\s#]+)/)
    errors << "#{name}: branch must be #{item['branch']}" if !branch || branch[1] != item["branch"]
    if item.fetch("type", "web") == "web"
      health = block.match(/^    healthCheckPath:\s*([^\s#]+)/)
      if !health || health[1] != item["health_path"]
        errors << "#{name}: healthCheckPath must be #{item['health_path']}"
      end
    end
    missing = (item.fetch("environment_contract") - required_keys(block)).sort
    errors << "#{name}: missing environment contract keys: #{missing.join(', ')}" unless missing.empty?
  end

  retired = inventory.fetch("retired_render_services")
  overlap = retired & render_services.keys
  unless overlap.empty?
    errors << "retired Render services must not be declared in render.yaml: #{overlap.sort.join(', ')}"
  end

  unless errors.empty?
    errors.each { |error| puts "ERROR: #{error}" }
    return 1
  end
  puts "Service inventory matches render.yaml: #{expected.length} canonical services; " \
       "#{retired.length} retired services excluded"
  0
end

exit(main) if $PROGRAM_NAME == __FILE__
